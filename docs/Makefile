# Minimal makefile for Sphinx documentation

# You can set these variables from the command line.
SOURCEDIR     = source
BUILDDIR      = .

.PHONY: clean

install:
	pip3 install sphinx sphinx-rtd-theme sphinx-autodoc-typehints ghp-import
	rm -rf source/modules
	mkdir -p source/modules
	cd source/modules && git clone --branch main --depth 1 -- https://github.com/sublimelsp/LSP.git
	sed -i -E 's/sublime\.DRAW_[A-Z_]*/0/g' source/modules/LSP/plugin/core/views.py

build:
	sphinx-build -M html "$(SOURCEDIR)" "$(BUILDDIR)"

deploy:
	ghp-import --no-jekyll --push --force html

clean:
	rm -rf doctrees html source/modules
