# lsp_utils

Module with LSP-related utilities for Sublime Text.

## How to use

1. Create a `dependencies.json` file in your package root with the following contents:

    ```json
    {
       "*": {
          "*": [
             "lsp_utils",
             "sublime_lib"
          ]
       }
    }
    ```

2. Run the **Package Control: Satisfy Dependencies** command via command palette.

See also documentation on [dependencies](https://packagecontrol.io/docs/dependencies).
