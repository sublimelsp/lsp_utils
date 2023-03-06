# LSP utilities for Package Control

Module with LSP-related utilities for Sublime Text

📘 [Documentation](https://sublimelsp.github.io/lsp_utils/)

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

2. Run the **Package Control: Satisfy Dependencies** command via the _Command Palette_.

See also [Documentation on Dependencies](https://packagecontrol.io/docs/dependencies)
