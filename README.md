# Unofficial fork of Python interface to Framsticks

This repository does not include some Python modules, such as "gui" or "evolalg".
They are still available on the official site.


Framsticks can be found here:

- website: https://www.framsticks.com/
- "framspy" source code
  - SVN: https://www.framsticks.com/svn/framsticks/framspy/
    - The original `Framsticks.zip` file is missing some `*.sim` files, but you can get them from this link.
  - trac: https://www.framsticks.com/trac/framsticks/browser/framspy/
  - interface to SDK in "/cpp" subfolder https://www.framsticks.com/svn/framsticks/cpp/
- [Framsticks SDK license](https://www.framsticks.com/svn/framsticks/cpp/LICENSE.txt)

## How to install?

You can install this package directly from Github. Using pip:

```
pip install git+https://github.com/jotpacanowski/framspy-fork.git
```

Using [uv](https://docs.astral.sh/uv/):

```
uv venv --seed .venv
uv add git+https://github.com/jotpacanowski/framspy-fork.git
```

## Test run

Download [Framsticks.zip](https://www.framsticks.com/files/apps/Framsticks.zip) from framsticks.com and unpack it.
The `FramsticksLib` and `frams` modules will need a path to folder
containing `frams-objects.dll` and `frams-objects.so` libraries.

<!-- Also note where the `data/` subdirectory is. -->
<!-- TODO: copy *.sim files from framspy? -->

[uv run](https://docs.astral.sh/uv/reference/cli/#uv-run) automatically activates virtualenv.

```
uv run python -m frams_test path/to/Framsticks52/
```

In Jupyter notebook, or if virtual environment is active, try:

```
!python -m frams_test path/to/Framsticks52/
```

## Detailed Framsticks classes documentation

Go to https://www.framsticks.com/files/classdoc/ and click on "GenMan".

To find mutation or crossover parameters, search for "f1_" or "f9_mut".

<!-- TODO: mutate and crossover C++ impl. - links from tutorial? -->


## Original description - "framspy" directory

This directory contains sources that allow one to interact with the native
Framsticks library from Python, and to perform evolutionary optimization.

"frams.py" is the most fundamental file. It allows to access Framsticks script
objects in Python. You will find detailed descriptions in the source of this file,
but since this file is only responsible for buidling the low-level bridge between
Framsticks and Python, understanding and modifying it should not be necessary.

"frams-test.py" uses "frams.py" and tests the connection between Python
and the native Framsticks library by performing a number of simple yet diversified
operations, so you should run it first to ensure everything works correctly.
This file can also be treated as a set of examples and demonstrations on how to access
Framsticks genotypes, the simulation, body parts, neurons, etc.
Again, read the comments in the source for more information.

"FramsticksLib.py" uses "frams.py" and provides a few fundamental, high-level building blocks
for optimization: functions to mutate, crossover, evaluate a solution, etc.

There are three independent implementations of evolutionary algorithms in this directory
and they all rely on "FramsticksLib.py":

1) "FramsticksEvolution.py" - the simplest one, everything is in one file. Uses the DEAP
    framework ( https://deap.readthedocs.io/en/master/ ) to perform the optimization.
    Supports multiple criteria, the generational architecture, and numerous parameters
    to customize the evolutionary search.
    See "run-deap-examples.cmd".

2)  The "evolalg_steps" module - the most complicated one, every piece of an algorithm
    is considered a "step" and can be customized. This results in a large number of small
    files (classes), but allows for the highest flexibility in building new algorithms.
    This module is no longer supported, but basic usage scenarios should work correctly.
    See "run-evolalg_steps-examples.cmd".

3)  The "evolalg" module - the middle ground. Minimalistic yet it allows for easy
    customizations, supports the generational architecture, the island model, quality-diversity
    techniques and numerical optimization (completely independent from Framsticks).
    Invalid genotypes are not accepted, so new ones are generated until they are valid.
    See "run-evolalg-examples.cmd".
