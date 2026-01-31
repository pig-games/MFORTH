# MFORTH #

This project is a fork of MFORTH by Michael Alyn Miller (actually a fork of the fork by [AbortRetryFail](https://github.com/AbortRetryFail/MFORTH)).
It includes a new build system and toolchain migration (opForge) by Erik van der Tier.

[ANS Forth](http://en.wikipedia.org/wiki/ANS_Forth) environment for the
[TRS-80 Model 100](http://en.wikipedia.org/wiki/Model_100) laptop
computer.  ROM images and additional information are available at the
[MFORTH](http://www.strangeGizmo.com/products/mforth/) page on
strangeGizmo.com.

## Compilation ##

The majority of MFORTH is written in 8085 assembly language and targets
[asm485](https://github.com/pig-games/asm485).

This fork of MFORTH supports a native build using **[opForge](https://github.com/pig-games/opForge)** and a `Makefile`.
The MFORTH sources in `src/` have been translated to asm485 syntax. The 
build mirrors the original two-pass process (first pass builds without PHASH, 
PhashGen emits `phash.asm`, second pass builds with PHASH).

MFORTH uses a perfect hash table to accelerate its access to the
ROM-based dictionary.  The first build pass creates the standard ROM,
with the traditional, linked list dictionary structure. MFORTH's
PhashGen tool then reads the dictionary out of the ROM file, generates
the hash tables, and writes those hash tables out as an assembler file.
The second build pass compiles the hash tables into the ROM and enables
the hash-based dictionary search.

Prerequisites:

- \`[opForge](https://github.com/pig-games/opForge)\` built locally (default: `tools/opforge`). Override with `OPFORGE=/path/to/opforge`.
- Rust toolchain (`cargo`) for the Rust PhashGen implementation
- Python 3

Build:

```bash
make clean
make
```

Output ROM binary is written to `bin/MFORTH.BX` (32 KiB).

Options (Rust PhashGen is the default):

```bash
make PROFILER=1
make MFORTH_CHANGE=1234
make PHASHGEN_IMPL=rust
```

`MFORTH_CHANGE` is passed through as a preprocessor define; no manual
regeneration is needed.

Notes:

If the symbol-extraction step fails (depends on asm85 listing formatting),
edit `tools/asm485_lst_to_sym.py` to match your local asm85 `.lst` format.

## Installation ##

MFORTH must be added to the system menu before it can be used. Perform
the following steps on your Model 100 or Model 102 laptop in order to
use MFORTH for the first time:

1.  Select BASIC from the system menu.
2.  Type `CALL 63012` at the `Ok` prompt and hit ENTER.
3.  MFORTH will load and add itself to the system menu.
4.  Type `bye` to return to the system menu. MFORTH should now appear on
    the system menu and can be accessed by selecting MFORTH and pressing
    ENTER.

## Usage ##

You can use the M100's TEXT editor to write programs for MFORTH.  Type
the programs into a new .DO file and then load them with MFORTH using
the following phrase (assuming that you named your file "TEST.DO"):

    S" TEST" INCLUDED

Note the space after the `S"` word.  Also, note that MFORTH is not case
sensitive when it comes to words, but that it is case sensitive when it
comes to file names.  In other words, you could also type the following
phrase to load the file:

    s" TEST" included

MFORTH supports multiple levels of file inclusion, so you could create a
MAIN.DO file that includes other .DO files.  This might make it easier
to structure and test your program.  You could put common utility words
in a file called UTILS.DO and then test those words in MFORTH by
including UTILS.DO.  Later, when you are ready to run your entire
program, you could include MAIN.DO.  MAIN.DO would include those other
files and then call the main entry point for your program.

## 8085 Assembler ##

MFORTH includes a full 8085 assembler, allowing easy access to the
M100's ROM routines or to improve the performance of key words.  The
assembler is accessed from the `ASSEMBLER` wordlist.

The assembler creates Forth words that can be called as part of a normal
Forth definition or from the interpreter.  The following code gives you
access to the Main ROM's `PLOT` routine, which draws a pixel at any
location on the screen:

    code plot ( x y --)
      saveregs
      h pop  l e mov
      h pop  l d mov
      29772 romcall
      restoreregs next
    end-code

You can then use `PLOT` just like any other MFORTH word:

    120 30 plot  120 31 plot  120 32 plot  120 33 plot

Note that the MFORTH assembler is a traditional, postfix assembler, so
the arguments are "reversed" from how they might look in something like
TASM.  The benefit of this approach is that the assembler has all of the
power of the Forth environment, so you can easily write loops and if
statements without having to deal with labels.  Here is an example of a
word that converts a lower case string to upper case:

    hex
    code toupper ( c-addr u --)
       saveregs
       d pop  h pop
       begin
          d a mov  e ora  0<>
       while
          m a mov  60 cpi  cc
          if  20 sui  a m mov  then
          d dcx  h inx
       repeat
       restoreregs next
    end-code
    decimal

Here is how to use the new word:

    S" Hello World"  2DUP TOUPPER TYPE

(outputs `HELLO WORLD`)

## Multitasker ##

MFORTH includes a cooperative multitasking system based on the `PAUSE`
word.  You can create multiple tasks and have them execute alongside
each other, even while you are writing more code and interacting with
MFORTH.  Tasks are very small (256 bytes).  Tasks are created by passing
an xt to the `TASK` word; the task will then run that xt until it
returns (which, in most cases, it should never do).  Tasks can suspend
themselves and give time to the next task by calling `PAUSE` and should
do that fairly often.  The primary task (the one that provides the text
interpreter) calls `PAUSE` every time it checks the keyboard queue, for
example.

Here is an example of a task that displays a clock in the upper-right
corner of the screen.  The clock will continue to update, even as you do
other things in MFORTH:

    : .NN ( u) 0 <# # # #> TYPE ;
    : .NNNN ( u) 0 <# # # # # #> TYPE ;
    : .-  [CHAR] - EMIT ;
    : .DATE ( d m y) .NNNN .- .NN .- .NN ;
    : .:  [CHAR] : EMIT ;
    : .TIME ( s m h) .NN .: .NN .: .NN ;
    : .TIME&DATE  TIME&DATE .DATE SPACE .TIME ;
    : SEC ( --u) TIME&DATE 2DROP 2DROP DROP ;
    : NEWSEC? ( u1--u2 f) SEC TUCK <> ;
    : .CLOCK  GET-XY  21 0 AT-XY  .TIME&DATE  AT-XY ;
    : CLOCK  0 BEGIN NEWSEC? IF .CLOCK THEN PAUSE AGAIN ;

You start the clock by typing:

    ' CLOCK TASK

There is no way to stop the clock display other than to exit MFORTH.

## Copyright and License ##

Copyright &copy; 2009-2012, Michael Alyn Miller <malyn@strangeGizmo.com>
Copyright (c) 2026, Erik van der Tier
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

1. Redistributions of source code must retain the above copyright notice
   unmodified, this list of conditions, and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright
   notice, this list of conditions and the following disclaimer in the
   documentation and/or other materials provided with the distribution.
3. Neither the name of Michael Alyn Miller nor the names of the
   contributors to this software may be used to endorse or promote
   products derived from this software without specific prior written
   permission.

THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS "AS IS" AND ANY
EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF
THE POSSIBILITY OF SUCH DAMAGE.
