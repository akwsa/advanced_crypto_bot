import ast
import os
import sys

def get_defined_functions_and_classes(filepath):
    try:
        with open(filepath, 'r') as f:
            tree = ast.parse(f.read())
    except:
        return set(), set()
    funcs = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    classes = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    return funcs, classes

def scan_project(root_dir):
    all_files = []
    for dirpath, _, filenames in os.walk(root_dir):
        if 'venv' in dirpath or '__pycache__' in dirpath or '.git' in dirpath:
            continue
        for f in filenames:
            if f.endswith('.py'):
                all_files.append(os.path.join(dirpath, f))

    print(f"Scanned {len(all_files)} files.")

    # Just search for "unused" or "not connected" by grepping the files for definitions and usages.
    definitions = {}
    for f in all_files:
        funcs, classes = get_defined_functions_and_classes(f)
        for name in funcs.union(classes):
            if name.startswith('__'): continue
            definitions[name] = f

    # naive grep for usages
    usages = {name: 0 for name in definitions}
    for f in all_files:
        try:
            with open(f, 'r') as file:
                content = file.read()
                for name in usages:
                    if name in content:
                        # count matches
                        import re
                        count = len(re.findall(r'\b' + name + r'\b', content))
                        usages[name] += count
        except:
            pass
            
    unused = []
    for name, count in usages.items():
        if count <= 1: # Only defined, never used elsewhere or even in the same file!
            unused.append((name, definitions[name]))
            
    for name, f in unused:
        print(f"Potentially unused: {name} in {os.path.relpath(f, root_dir)}")

if __name__ == "__main__":
    scan_project("/home/officer/advanced_crypto_bot/advanced_crypto_bot")
