# Minimal makefile for Sphinx documentation

# You can set these variables from the command line.
SOURCEDIR     = source
BUILDDIR      = .

.PHONY: clean

install:
	pip3 install sphinx sphinx-rtd-theme sphinx-autodoc-typehints ghp-import
	rm -rf source/modules
	mkdir -p source/modules
	cd source/modules && git clone --branch st4000-exploration --depth 1 -- https://github.com/sublimelsp/LSP.git

build:
	sphinx-build -M html "$(SOURCEDIR)" "$(BUILDDIR)"

deploy:
	ghp-import --no-jekyll --push --force html

clean:
	rm -rf doctrees html source/modules
