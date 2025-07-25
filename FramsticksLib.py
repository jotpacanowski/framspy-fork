import argparse
import json
import os
import random
import sys
from enum import Enum, auto, unique

import numpy as np

import frams

# from typing import List  # to be able to specify a type hint of list(something)


@unique
class DissimMethod(Enum):  # values assigned to fields are irrelevant, hence auto()
    GENE_LEVENSHTEIN = auto()  # genetic Levenshtein distance
    PHENE_STRUCT_GREEDY = auto()  # phenetic, graph structure, fast but approximate
    PHENE_STRUCT_OPTIM = auto()  # phenetic, graph structure, slower for complex creatures but optimal
    PHENE_DESCRIPTORS = auto()  # phenetic, shape descriptors
    PHENE_DENSITY_COUNT = auto()  # phenetic, density distribution, count of samples
    PHENE_DENSITY_FREQ = auto()  # phenetic, density distribution, frequency of count of samples
    FITNESS = auto()  # fitness value


class FramsticksLib:
    """Communicates directly with Framsticks library (.dll or .so or .dylib).
    You can perform basic operations like mutation, crossover, and evaluation of genotypes.
    This way you can perform evolution controlled by python as well as access and manipulate genotypes.
    You can even design and use in evolution your own genetic representation implemented entirely in python,
    or access and control the simulation and simulated creatures step by step.

    Should you want to modify or extend this class, first see and test the examples in frams-test.py.

    You need to provide one or two parameters when you run this class: the path to Framsticks where .dll/.so/.dylib resides
    and, optionally, the name of the Framsticks dll/so/dylib (if it is non-standard). See::
        FramsticksLib.py -h"""

    PRINT_FRAMSTICKS_OUTPUT: bool = False
    "Set to True for debugging."
    DETERMINISTIC: bool = False
    """Set to True to have the same results in each run.
    
    Must be set before FramsticksLib() constructor call.
    """

    GENOTYPE_INVALID: str = "/*invalid*/"
    """
    This is how genotype invalidity is represented in Framsticks (Geno.format is 'invalid').
    Mutation and crossover operators return such a genotype if they were unable to perform their operation
    (information about the cause is stored in the Geno.info field - see GenMan.cpp)
    """
    GENOTYPE_INVALID_OFFSPRING_SUBSTITUTE_ORIGINAL: bool = True
    """
    if True, when mutation or crossover is unable to perform their operation for the provided genotype(s),
    return the original genotype (and print a warning). If this happens extremely rarely, it may be ignored - but if not,
    you need to identify the reason (e.g., particular genotypes that cause the problem), fix it or change the logic of your algorithm.
    A more strict approach is to keep this field False - then you must always check if GENOTYPE_INVALID was returned by mutate() or crossOver(),
    and handle this situation properly (e.g., choose different parent(s) for mutate() or crossOver() and repeat until you get a valid offspring).
    """

    EVALUATION_SETTINGS_FILE = [
        "eval-allcriteria.sim",  # a good trade-off in performance sampling period ("perfperiod") for vertpos and velocity
        # "deterministic.sim",  # turns off random noise (added for robustness) so that each evaluation yields identical performance values (causes "overfitting")
        # "sample-period-2.sim", # short performance sampling period so performance (e.g. vertical position) is sampled more often
        # "sample-period-longest.sim",  # increased performance sampling period so distance and velocity are measured rectilinearly
    ]
    """All files MUST be compatible with the standard-eval expdef.
    The order they are loaded in is important!
    """

    # This function is not needed because in Python, "For efficiency reasons, each module is only imported once per interpreter session."
    # @staticmethod
    # def getFramsModuleInstance():
    # """If some other party needs access to the frams module to directly access or modify Framsticks objects,
    # use this function to avoid importing the "frams" module multiple times and avoid potentially initializing
    # it many times."""
    # return frams

    def __init__(self, frams_path, frams_lib_name, sim_settings_files):
        # will be initialized only when necessary (for rare dissimilarity methods)
        self.dissim_measure_density_distribution = None

        if frams_lib_name is None:
            # could add support for setting alternative directories using -D and -d
            frams.init(frams_path)
        else:
            # could add support for setting alternative directories using -D and -d
            frams.init(frams_path, "-L" + frams_lib_name)

        print("Available objects:", dir(frams))
        print()

        simplest = self.getSimplest("1")
        if not (simplest == "X" and type(simplest) is str):
            raise RuntimeError("Failed getSimplest() test.")
        if not (self.isValid(["X[0:0],", "X[0:0]", "X[1:0]"]) == [False, True, False]):
            raise RuntimeError("Failed isValid() test.")

        if not self.DETERMINISTIC:
            frams.Math.randomize()
        frams.Simulator.expdef = "standard-eval"  # this expdef (or fully compatible) must be used by EVALUATION_SETTINGS_FILE
        if sim_settings_files is not None:
            self.EVALUATION_SETTINGS_FILE = sim_settings_files.split(";")  # override defaults. str becomes list
        print("Basic tests OK. Using settings:", self.EVALUATION_SETTINGS_FILE)
        print()

        for simfile in self.EVALUATION_SETTINGS_FILE:
            ec = frams.MessageCatcher.new()  # catch potential errors, warnings, messages - just to detect if there are ERRORs
            ec.store = 2  # store all, because they are caught by MessageCatcher and will not appear in output (which we want)
            frams.Simulator.ximport(simfile, 4 + 8 + 16)
            ec.close()
            print(ec.messages)  # output all caught messages
            if ec.error_count._value() > 0:
                # make missing files or incorrect paths fatal because error messages are easy to overlook in output,
                #  and these errors would not prevent Framsticks simulator from performing genetic operations, starting and running in evaluate()
                raise ValueError("Problem while importing file '%s'" % simfile)

    @staticmethod
    def shortGenotype(genotype: str) -> str:
        """
        Returns a few initial characters of the genotype, just for information/identifying the genotype.
        """
        return repr(genotype) if len(genotype) <= 10 else repr(genotype[:10] + "...")

    def getSimplest(self, genetic_format: str) -> str:
        return frams.GenMan.getSimplest(genetic_format).genotype._string()

    def getPJNC(self, genotype: str):
        """
        Returns the number of elements of a phenotype built from the provided genotype (without any simulation).

        :param genotype: the genotype to assess
        :return: a tuple of (numparts,numjoints,numneurons,numconnections) or None if the genotype is invalid.
        """
        model = frams.Model.newFromString(genotype)
        if model.is_valid._int() == 0:
            return None
        return (model.numparts._int(), model.numjoints._int(), model.numneurons._int(), model.numconnections._int())

    def satisfiesConstraints(
        self,
        genotype: str,
        max_numparts: int,
        max_numjoints: int,
        max_numneurons: int,
        max_numconnections: int,
        max_numgenochars: int,
    ) -> bool:
        """
        Verifies if the genotype satisfies complexity constraints without actually simulating it.

        For example, if the genotype represents a phenotype with 1000 Parts, it will be much faster to check it using this function
        than to simulate the resulting creature using evaluate() only to learn that the number of its Parts exceeds your defined limit.

        :param genotype: the genotype to check
        :return: False if any constraint is violated or the genotype is invalid, else True. The constraint value of None means no constraint.
        """

        def value_within_constraint(actual_value, constraint_value):
            if constraint_value is not None:
                if actual_value > constraint_value:
                    return False
            return True

        PJNC = self.getPJNC(genotype)
        if PJNC is None:
            return False  # Let's treat invalid genotypes as not satisfying constraints
        P, J, N, C = PJNC

        valid = True
        valid &= value_within_constraint(len(genotype), max_numgenochars)
        valid &= value_within_constraint(P, max_numparts)
        valid &= value_within_constraint(J, max_numjoints)
        valid &= value_within_constraint(N, max_numneurons)
        valid &= value_within_constraint(C, max_numconnections)
        return valid

    def evaluate(self, genotype_list: list[str]):
        """
        Returns:
            List of dictionaries containing the performance of genotypes evaluated using self.EVALUATION_SETTINGS_FILE.
            Note that for whatever reason (e.g. incorrect genotype), the dictionaries you will get may be empty or
            partially empty and may not have the fields you expected, so handle such cases properly.
        """
        assert isinstance(
            genotype_list, list
        )  # because in python, str has similar capabilities as list and here it would pretend to work too, so to avoid any ambiguity

        if not self.PRINT_FRAMSTICKS_OUTPUT:
            ec = frams.MessageCatcher.new()  # mute potential errors, warnings, messages
            ec.store = 2  # store all, because they are caught by MessageCatcher and will not appear in output

        frams.GenePools[0].clear()
        for g in genotype_list:
            frams.GenePools[0].add(g)
        frams.ExpProperties.evalsavefile = (
            ""  # no need to store results in a file - we will get evaluations directly from Genotype's "data" field
        )
        frams.Simulator.init()
        frams.Simulator.start()

        # step = frams.Simulator.step  # cache reference to avoid repeated lookup in the loop (just for performance)
        # while frams.Simulator.running._int():  # standard-eval.expdef sets running to 0 when the evaluation is complete
        # step()
        frams.Simulator.eval("while(Simulator.running) Simulator.step();")  # fastest
        # Timing for evaluating a single simple creature 100x:
        # - python step without caching: 2.2s
        # - python step with caching   : 1.6s
        # - pure FramScript and eval() : 0.4s

        if not self.PRINT_FRAMSTICKS_OUTPUT:
            ec.close()
            if ec.error_count._value() > 0:
                print("\nErrors while evaluating this genotype list:\n", genotype_list, sep="\t")
                print(ec.messages)  # if errors occurred, output all caught messages for debugging
                # make errors fatal; by default they stop the simulation anyway so let's not use potentially incorrect or partial results and fix the cause first.
                raise RuntimeError(
                    "[ERROR] %d error(s) and %d warning(s) while evaluating %d genotype(s)"
                    % (ec.error_count._value(), ec.warning_count._value(), len(genotype_list))
                )

        results = []
        for g in frams.GenePools[0]:
            serialized_dict = frams.String.serialize(g.data[frams.ExpProperties.evalsavedata._value()])
            evaluations = json.loads(
                serialized_dict._string()
            )  # Framsticks native ExtValue's get converted to native python types such as int, float, list, str.
            # now, for consistency with FramsticksCLI.py, add "num" and "name" keys that are missing because we got data directly from Genotype,
            #  not from the file produced by standard-eval.expdef's function printStats(). What we do below is what printStats() does.
            result = {"num": g.num._value(), "name": g.name._value(), "evaluations": evaluations}
            results.append(result)

        return results

    def mutate(self, genotype_list: list[str]) -> list[str]:
        """
        Returns:
            The genotype(s) of the mutated source genotype(s). self.GENOTYPE_INVALID for genotypes whose mutation failed (for example because the source genotype was invalid).
        """
        assert isinstance(
            genotype_list, list
        )  # because in python, str has similar capabilities as list and here it would pretend to work too, so to avoid any ambiguity

        mutated = []
        for genotype_parent in genotype_list:
            offspring = frams.GenMan.mutate(frams.Geno.newFromString(genotype_parent))
            offspring_genotype = offspring.genotype._string()
            if offspring_genotype == self.GENOTYPE_INVALID and self.GENOTYPE_INVALID_OFFSPRING_SUBSTITUTE_ORIGINAL:
                print(
                    "[WARN] mutate(%s) failed but you requested GENOTYPE_INVALID_OFFSPRING_SUBSTITUTE_ORIGINAL, so returning the original genotype instead. Reason for failure: %s"
                    % (self.shortGenotype(genotype_parent), offspring.info._string())
                )
                offspring_genotype = genotype_parent
            mutated.append(offspring_genotype)
        if len(genotype_list) != len(mutated):
            raise RuntimeError("Submitted %d genotypes, received %d mutants" % (len(genotype_list), len(mutated)))
        return mutated

    def crossOver(self, genotype_parent1: str, genotype_parent2: str) -> str:
        """
        Returns:
            The genotype of the offspring. self.GENOTYPE_INVALID if the crossing over failed.
        """
        offspring = frams.GenMan.crossOver(frams.Geno.newFromString(genotype_parent1), frams.Geno.newFromString(genotype_parent2))
        offspring_genotype = offspring.genotype._string()
        if offspring_genotype == self.GENOTYPE_INVALID and self.GENOTYPE_INVALID_OFFSPRING_SUBSTITUTE_ORIGINAL:
            print(
                "[WARN] crossOver(%s, %s) failed but you requested GENOTYPE_INVALID_OFFSPRING_SUBSTITUTE_ORIGINAL, so returning a random parent instead. Reason for failure: %s"
                % (self.shortGenotype(genotype_parent1), self.shortGenotype(genotype_parent2), offspring.info._string())
            )
            offspring_genotype = random.choice([genotype_parent1, genotype_parent2])
        return offspring_genotype

    def dissimilarity(self, genotype_list: list[str], method: DissimMethod) -> np.ndarray:
        """
        :param method, see DissimMethod.
        :return: A square array with dissimilarities of each pair of genotypes.
        """
        assert isinstance(
            genotype_list, list
        )  # because in python, str has similar capabilities as list and here it would pretend to work too, so to avoid any ambiguity

        # if you want to override what EVALUATION_SETTINGS_FILE sets, you can do it below:
        # frams.SimilMeasureHungarian.simil_partgeom = 1
        # frams.SimilMeasureHungarian.simil_weightedMDS = 1

        n = len(genotype_list)
        square_matrix = np.zeros((n, n))

        if method in (
            DissimMethod.PHENE_STRUCT_GREEDY,
            DissimMethod.PHENE_STRUCT_OPTIM,
            DissimMethod.PHENE_DESCRIPTORS,
        ):  # Framsticks phenetic dissimilarity methods
            frams.SimilMeasure.simil_type = (
                0 if method == DissimMethod.PHENE_STRUCT_GREEDY else 1 if method == DissimMethod.PHENE_STRUCT_OPTIM else 2
            )
            genos = []  # prepare an array of Geno objects so that we don't need to convert raw strings to Geno objects all the time in loops
            for g in genotype_list:
                genos.append(frams.Geno.newFromString(g))
            frams_evaluateDistance = (
                frams.SimilMeasure.evaluateDistance
            )  # cache function reference for better performance in loops
            for i in range(n):
                for j in range(n):  # maybe calculate only one triangle if you really need a 2x speedup
                    square_matrix[i][j] = frams_evaluateDistance(genos[i], genos[j])._double()
        elif method == DissimMethod.GENE_LEVENSHTEIN:
            import Levenshtein

            for i in range(n):
                for j in range(n):  # maybe calculate only one triangle if you really need a 2x speedup
                    square_matrix[i][j] = Levenshtein.distance(genotype_list[i], genotype_list[j])
        elif method in (DissimMethod.PHENE_DENSITY_COUNT, DissimMethod.PHENE_DENSITY_FREQ):
            if self.dissim_measure_density_distribution is None:
                from dissimilarity.density_distribution import DensityDistribution

                self.dissim_measure_density_distribution = DensityDistribution(frams)
            self.dissim_measure_density_distribution.frequency = method == DissimMethod.PHENE_DENSITY_FREQ
            square_matrix = self.dissim_measure_density_distribution.getDissimilarityMatrix(genotype_list)
        else:
            raise ValueError("Don't know what to do with dissimilarity method = %s" % method)

        for i in range(n):
            assert square_matrix[i][i] == 0, "Not a correct dissimilarity matrix, diagonal expected to be 0"
        non_symmetric_diff = square_matrix - square_matrix.T
        non_symmetric_count = np.count_nonzero(non_symmetric_diff)
        if non_symmetric_count > 0:
            non_symmetric_diff_abs = np.abs(non_symmetric_diff)
            max_pos1d = np.argmax(non_symmetric_diff_abs)  # location of the largest discrepancy
            max_pos2d_XY = np.unravel_index(max_pos1d, non_symmetric_diff_abs.shape)  # 2D coordinates of the largest discrepancy
            max_pos2d_YX = max_pos2d_XY[1], max_pos2d_XY[0]  # 2D coordinates of the largest discrepancy mirror
            worst_guy_XY = square_matrix[max_pos2d_XY]  # this distance and the other below (its mirror) are most different
            worst_guy_YX = square_matrix[max_pos2d_YX]
            print(
                "[WARN] Dissimilarity matrix: expecting symmetry, but %g out of %d pairs were asymmetrical, max difference was %g (%g %%)"
                % (
                    non_symmetric_count / 2,
                    n * (n - 1) / 2,
                    non_symmetric_diff_abs[max_pos2d_XY],
                    non_symmetric_diff_abs[max_pos2d_XY] * 100 / ((worst_guy_XY + worst_guy_YX) / 2),
                )
            )  # max diff is not necessarily max %
        return square_matrix

    def getRandomGenotype(
        self,
        initial_genotype: str,
        parts_min: int,
        parts_max: int,
        neurons_min: int,
        neurons_max: int,
        iter_max: int,
        return_even_if_failed: bool,
    ):
        """
        Some algorithms require a "random solution". To this end, this method generates a random framstick genotype.

        :param initial_genotype: if not a specific genotype (which could facilitate greater variability of returned genotypes), try `getSimplest(format)`.
        :param iter_max: how many mutations can be used to generate a random genotype that fullfills target numbers of parts and neurons.
        :param return_even_if_failed: if the target numbers of parts and neurons was not achieved, return the closest genotype that was found?
            Set it to False first to experimentally adjust `iter_max` so that in most calls this function returns a genotype with target numbers of parts and neurons,
            and then you can set this parameter to True if target numbers of parts and neurons are not absolutely required.
        :returns: a valid genotype or None if failed and `return_even_if_failed` is False.
        """

        def estimate_diff(g: str):
            if not self.isValidCreature([g])[0]:
                return None, None
            m = frams.Model.newFromString(g)
            numparts = m.numparts._value()
            numneurons = m.numneurons._value()
            diff_parts = abs(target_parts - numparts)
            diff_neurons = abs(target_neurons - numneurons)
            in_target_range = (parts_min <= numparts <= parts_max) and (
                neurons_min <= numneurons <= neurons_max
            )  # less demanding than precisely reaching target_parts and target_neurons
            return diff_parts + diff_neurons, in_target_range

        # try to find a genotype that matches the number of parts and neurons randomly selected from the provided min..max range
        # (even if we fail to match this precise target, the goal will be achieved if the found genotype manages to be within min..max ranges for parts and neurons)
        target_parts = np.random.default_rng().integers(parts_min, parts_max + 1)
        target_neurons = np.random.default_rng().integers(neurons_min, neurons_max + 1)

        if not self.isValidCreature([initial_genotype])[0]:
            raise ValueError("Initial genotype '%s' is invalid" % initial_genotype)

        g = initial_genotype
        for i in range(iter_max // 2):  # a sequence of iter_max/2 undirected mutations starting from initial_genotype
            g_new = self.mutate([g])[0]
            if self.isValidCreature([g_new])[0]:  # valid mutation
                g = g_new

        best_diff, best_in_target_range = estimate_diff(g)
        for i in range(
            iter_max // 2
        ):  # a sequence of iter_max/2 mutations, only accepting those which approach target numbers of parts and neurons
            g_new = self.mutate([g])[0]
            diff, in_target_range = estimate_diff(g_new)
            if diff is not None and diff <= best_diff:  # valid mutation and better or as good as current
                g = g_new
                best_diff = diff
                best_in_target_range = in_target_range
        # print(diff, best_diff) # print progress approaching target numbers of parts and neurons

        if best_in_target_range or return_even_if_failed:
            return g  # best found so far (closest to target numbers of parts and neurons)
        return None

    def isValid(self, genotype_list: list[str]) -> list[bool]:
        """
        :returns: genetic validity (i.e., not based on trying to build creatures from provided genotypes). For a more thorough check, see isValidCreature().
        """
        assert isinstance(
            genotype_list, list
        )  # because in python, str has similar capabilities as list and here it would pretend to work too, so to avoid any ambiguity
        valid = []
        for g in genotype_list:
            valid.append(frams.Geno.newFromString(g).is_valid._int() == 1)
        if len(genotype_list) != len(valid):
            raise RuntimeError("Tested %d genotypes, received %d validity values" % (len(genotype_list), len(valid)))
        return valid

    def isValidCreature(self, genotype_list: list[str]) -> list[bool]:
        """
        :returns: validity of the genotype when revived. Apart from genetic validity,
          this includes detecting problems that may arise when building a Creature from Genotype,
          such as multiple muscles of the same type in the same location in body, e.g. 'X[@][@]'.
        """

        # Genetic validity and simulator validity are two separate properties (in particular, genetic validity check is implemented by the author of a given genetic format and operators).
        # Thus, the subset of genotypes valid genetically and valid in simulation may be overlapping.
        # For example, 'X[]' or 'Xr' are considered invalid by the genetic checker, but the f1->f0 converter will ignore meaningless genes and produce a valid f0 genotype.
        # On the other hand, 'X[@][@]' or 'X[|][|]' are valid genetically, but not possible to simulate.
        # For simplicity of usage (so that one does not need to check both properties separately using both functions), let's make one validity a subset of the other.
        # The genetic check in the first lines of the "for" loop makes this function at least as demanding as isValid().

        assert isinstance(
            genotype_list, list
        )  # because in python, str has similar capabilities as list and here it would pretend to work too, so to avoid any ambiguity

        pop = frams.Populations[
            0
        ]  # assuming rules from population #0 (self-colision settings are population-dependent and can influence creature build success/failure)

        valid = []
        for g in genotype_list:
            if frams.Geno.newFromString(g).is_valid._int() != 1:
                valid.append(False)  # invalid according to genetic check
            else:
                # First "1" means to treat warnings during build as build failures
                #  - this allows detecting problems when building Creature from Genotype.
                # Second "1" means mute emitted errors, warnings, messages.
                # Returns 1 (ok, could add) or 0 (there were some problems building Creature from Genotype)
                can_add = pop.canAdd(g, 1, 1)
                valid.append(can_add._int() == 1)

        if len(genotype_list) != len(valid):
            raise RuntimeError("Tested %d genotypes, received %d validity values" % (len(genotype_list), len(valid)))
        return valid


def parseArguments():
    parser = argparse.ArgumentParser(
        description='Run this program with "python -u %s" if you want to disable buffering of its output.' % sys.argv[0]
    )
    parser.add_argument(
        "-path",
        type=ensureDir,
        required=True,
        help="Path to the Framsticks library (.dll or .so or .dylib) without trailing slash.",
    )
    parser.add_argument(
        "-lib",
        required=False,
        help='Library name. If not given, "frams-objects.dll" (or .so or .dylib) is assumed depending on the platform.',
    )
    parser.add_argument(
        "-simsettings",
        required=False,
        help="The name of the .sim file with settings for evaluation, mutation, crossover, and similarity estimation. "
        'If not given, "eval-allcriteria.sim" is assumed by default. Must be compatible with the "standard-eval" expdef. '
        "If you want to provide more files, separate them with a semicolon ';'.",
    )
    parser.add_argument(
        "-genformat", required=False, help="Genetic format for the demo run, for example 4, 9, or S. If not given, f1 is assumed."
    )
    return parser.parse_args()


def ensureDir(string):
    if os.path.isdir(string):
        return string
    else:
        raise NotADirectoryError(string)


if __name__ == "__main__":
    # A demo run.

    # TODO ideas:
    # - check_validity with three levels (invalid, corrected, valid)
    # - a pool of binaries running simultaneously, balance load - in particular evaluation

    parsed_args = parseArguments()
    framsLib = FramsticksLib(parsed_args.path, parsed_args.lib, parsed_args.simsettings)

    print('Sending a direct command to Framsticks library that calculates "4"+2 yields', frams.Simulator.eval('return "4"+2;'))

    simplest = framsLib.getSimplest("1" if parsed_args.genformat is None else parsed_args.genformat)
    print("\tSimplest genotype:", simplest)
    parent1 = framsLib.mutate([simplest])[0]
    parent2 = parent1
    MUTATE_COUNT = 10
    for x in range(MUTATE_COUNT):  # example of a chain of 10 mutations
        parent2 = framsLib.mutate([parent2])[0]
    print("\tParent1 (mutated simplest):", parent1)
    print("\tParent2 (Parent1 mutated %d times):" % MUTATE_COUNT, parent2)
    offspring = framsLib.crossOver(parent1, parent2)
    print("\tCrossover (Offspring):", offspring)
    print(
        "\tDissimilarity of Parent1 and Offspring:",
        framsLib.dissimilarity([parent1, offspring], DissimMethod.PHENE_STRUCT_OPTIM)[0, 1],
    )
    print("\tPerformance of Offspring:", framsLib.evaluate([offspring]))
    print("\tValidity (genetic) of Parent1, Parent 2, and Offspring:", framsLib.isValid([parent1, parent2, offspring]))
    print("\tValidity (simulation) of Parent1, Parent 2, and Offspring:", framsLib.isValidCreature([parent1, parent2, offspring]))
    print("\tValidity (constraints) of Offspring:", framsLib.satisfiesConstraints(offspring, 2, None, 5, 10, None))
    print("\tRandom genotype:", framsLib.getRandomGenotype(simplest, 2, 6, 2, 4, 100, True))
