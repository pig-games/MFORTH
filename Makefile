# macOS / Linux Makefile for MFORTH using opforge instead of Telemark TASM.
#
# Why this exists:
# - Original build.bat drives Telemark TASM + PhashGen, building twice (linked dictionary -> generate phash.asm -> build with PHASH).
# - opforge is native-friendly and now includes basic IF/ELSE/ELSEIF/ENDIF plus a small preprocessor (DEFINE/IFDEF/IFNDEF/INCLUDE).
# - The MFORTH sources in this repo are already in opforge syntax (no # directives, no dot directives).
#   The build is:
#     1) assemble pass1 without PHASH
#     2) run PhashGen to create src/phash.asm (already opforge syntax)
#     3) assemble pass2 with -DPHASH
#
# Requirements:
#   - dotnet SDK (build/run PhashGen)
#   - opforge (https://github.com/TomNisbet/opforge) built locally or on PATH

SHELL := /bin/bash
.ONESHELL:
.SUFFIXES:

ROOT := $(abspath .)
SRC  := $(ROOT)/src
BIN  := $(ROOT)/bin
TST  := $(ROOT)/test
BLD  := $(ROOT)/build

OPFORGE ?= $(ROOT)/tools/opforge

# Tools (repo-local)
LST2SYM := $(ROOT)/tools/opforge_lst_to_sym.py

# PhashGen implementation (csharp or rust)
PHASHGEN_IMPL ?= rust

# dotnet PhashGen project
PHASHGEN_PROJ := $(ROOT)/tools/depricated/PhashGenOld/PhashGen.csproj
PHASHGEN_OUT  := $(BLD)/PhashGenOld
PHASHGEN_SRCS := \
	$(ROOT)/tools/depricated/PhashGenOld/Program.cs \
	$(ROOT)/tools/depricated/PhashGenOld/Properties/AssemblyInfo.cs \
	$(ROOT)/tools/depricated/ToolLib/*.cs \
	$(ROOT)/tools/depricated/ToolLib/Properties/AssemblyInfo.cs

# Rust PhashGen project
PHASHGEN_RUST_DIR := $(ROOT)/tools/phashgen
PHASHGEN_RUST_BIN := $(PHASHGEN_RUST_DIR)/target/release/phashgen
PHASHGEN_RUST_SRCS := $(shell find "$(PHASHGEN_RUST_DIR)" -type f \( -name '*.rs' -o -name 'Cargo.toml' \))

# Outputs
PASS1_HEX := $(BLD)/MFORTH_pass1.hex
PASS1_LST := $(BLD)/MFORTH_pass1.lst
PASS1_BIN := $(BLD)/MFORTH_pass1.bin
PASS1_SYM := $(BLD)/MFORTH_pass1.sym
PASS1_BASE := $(BLD)/MFORTH_pass1

PASS2_HEX := $(BLD)/MFORTH.hex
PASS2_LST := $(BLD)/MFORTH.lst
PASS2_BIN := $(BIN)/MFORTH.BX
PASS2_SYM := $(BLD)/MFORTH.sym
PASS2_BASE := $(BLD)/MFORTH
BIN_RANGE := 0000:7FFF
BIN_FILL  ?= 00

PHASH_ASM := $(SRC)/phash.asm
MFORTH_MAIN := $(SRC)/main.asm
MFORTH_PHASH := $(SRC)/phash.asm
MFORTH_BUILD := $(BLD)/mforth_src
MFORTH_BUILD_MAIN := $(MFORTH_BUILD)/main.asm
MFORTH_BUILD_PHASH := $(MFORTH_BUILD)/phash.asm

# Version stamping: original build.bat uses Perforce change number.
# Default to 1201 to match the reference MFORTH.BX 2 binary; override as needed.
MFORTH_CHANGE ?= 1201

# Enable profiler build: make PROFILER=1
ifeq ($(PROFILER),1)
  PROF_DEF := -D PROFILER
else
  PROF_DEF :=
endif
MFORTH_DEF := -D MFORTH_CHANGE=$(MFORTH_CHANGE)
PASS1_DEFS := $(MFORTH_DEF) $(PROF_DEF)
PASS2_DEFS := $(PASS1_DEFS) -DPHASH

.PHONY: all test compare-bins
all: rom

.PHONY: rom
rom: $(PASS2_BIN)
	@echo "Built: $(PASS2_BIN)"

$(BLD):
	mkdir -p $(BLD)

$(MFORTH_BUILD_MAIN): $(MFORTH_MAIN) $(ROOT)/tools/strip_preproc_hash.py | $(BLD)
	python3 "$(ROOT)/tools/strip_preproc_hash.py" "$(SRC)" "$(MFORTH_BUILD)"

# --------------------------------------------------------------------
# Pass 1: build linked-list dictionary ROM (no PHASH)
# --------------------------------------------------------------------
$(PASS1_HEX) $(PASS1_LST) $(PASS1_BIN): $(MFORTH_BUILD_MAIN) | $(BLD)
	@echo "== opforge pass1 (no PHASH) =="
	cd "$(MFORTH_BUILD)" && \
	"$(OPFORGE)" $(PASS1_DEFS) -o "$(PASS1_BASE)" -l -x -b $(BIN_RANGE) -f $(BIN_FILL) -i "main.asm"

$(PASS1_SYM): $(PASS1_LST) | $(BLD)
	$(LST2SYM) "$(PASS1_LST)" "$(PASS1_SYM)"

# --------------------------------------------------------------------
# PhashGen: generate src/phash.asm (opforge syntax)
# --------------------------------------------------------------------
ifeq ($(PHASHGEN_IMPL),rust)
$(PHASH_ASM): $(PASS1_BIN) $(PASS1_SYM) $(PHASHGEN_RUST_SRCS) | $(BLD)
	@echo "== Building PhashGen (Rust) =="
	cargo build -p phashgen --release --manifest-path "$(PHASHGEN_RUST_DIR)/Cargo.toml"
	@echo "== Running PhashGen (Rust) =="
	"$(PHASHGEN_RUST_BIN)" "$(PASS1_BIN)" "$(PASS1_SYM)" "$(PHASH_ASM)"
else
$(PHASH_ASM): $(PASS1_BIN) $(PASS1_SYM) $(PHASHGEN_PROJ) $(PHASHGEN_SRCS) | $(BLD)
	@echo "== Building PhashGen =="
	dotnet build -c Release "$(PHASHGEN_PROJ)" -o "$(PHASHGEN_OUT)"
	@echo "== Running PhashGen =="
	# PhashGen.exe args: <rom> <sym> <outasm>
	dotnet "$(PHASHGEN_OUT)/PhashGen.dll" "$(PASS1_BIN)" "$(PASS1_SYM)" "$(PHASH_ASM)"
endif

$(MFORTH_BUILD_PHASH): $(MFORTH_PHASH) | $(BLD)
	python3 -c 'import shutil, pathlib; dst=pathlib.Path(r"$(MFORTH_BUILD)"); dst.mkdir(parents=True, exist_ok=True); shutil.copy2(r"$(MFORTH_PHASH)", dst / "phash.asm")'

# --------------------------------------------------------------------
# Pass 2: build PHASH-enabled ROM, output to bin/MFORTH.BX
# --------------------------------------------------------------------
$(PASS2_HEX) $(PASS2_LST) $(PASS2_BIN): $(MFORTH_BUILD_MAIN) $(MFORTH_BUILD_PHASH) | $(BLD)
	@echo "== opforge pass2 (PHASH) =="
	cd "$(MFORTH_BUILD)" && \
	"$(OPFORGE)" $(PASS2_DEFS) -o "$(PASS2_BASE)" -l -x -b $(BIN_RANGE) -f $(BIN_FILL) -i "main.asm" && \
	mkdir -p "$(BIN)" && \
	mv -f "$(PASS2_BASE).bin" "$(PASS2_BIN)"

.PHONY: clean
clean:
	rm -rf "$(BLD)"
	rm -f "$(PHASH_ASM)"

test:
	python3 "$(ROOT)/tools/tass_to_opforge/test/compare_conversion.py"

.PHONY: compare-bins
compare-bins:
	@echo "Comparing $(BIN)/MFORTH.BX and $(TST)/Reference.bx"
	@shasum -a 256 "$(PASS2_BIN)" "$(TST)/Reference.bx"
	@if cmp -s "$(PASS2_BIN)" "$(TST)/Reference.bx"; then \
		echo "IDENTICAL"; \
	else \
		echo "DIFFER (showing first 200 differing bytes)"; \
		cmp -l "$(PASS2_BIN)" "$(TST)/Reference.bx" | head -n 200; \
		echo "Hex diff (first 200 lines):"; \
		diff -u <(xxd "$(PASS2_BIN)") <(xxd "$(TST)/Reference.bx") | sed -n '1,200p'; \
		false; \
	fi