# LSP utilities for Package Control

Module with LSP-related utilities for Sublime Text

## How to use

1. Create a `dependencies.json` file in your package root with the following contents:

    ```js
    {
       "*": {
          "*": [
             "lsp_utils",
             "sublime_lib"
          ]
       }
    }
    ```

2. Run the **Package Control: Satisfy Dependencies** command via command palette

3. Import utility:

    ```python
    from lsp_utils import ServerNpmResource
    ```

See also:
[Documentation on Dependencies](https://packagecontrol.io/docs/dependencies)
