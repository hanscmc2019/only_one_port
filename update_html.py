import os
import re

html_dir = 'web/'
html_files = [f for f in os.listdir(html_dir) if f.endswith('.html')]

topbar_pattern = re.compile(r'<!-- Topbar Start -->.*?<!-- Topbar End -->', re.DOTALL)
navbar_pattern = re.compile(r'<!-- Navbar Start -->.*?<!-- Navbar End -->', re.DOTALL)

for file in html_files:
    if file.startswith('components'):
        continue
    path = os.path.join(html_dir, file)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    modified = False
    
    # Generate the navbar components before modifying
    if file == 'index.html':
        navbar_match = navbar_pattern.search(content)
        if navbar_match:
            with open(os.path.join(html_dir, 'components', 'navbar_home.html'), 'w', encoding='utf-8') as comp_file:
                comp_file.write(navbar_match.group(0))
    elif file == 'shop.html':
        navbar_match = navbar_pattern.search(content)
        if navbar_match:
            with open(os.path.join(html_dir, 'components', 'navbar.html'), 'w', encoding='utf-8') as comp_file:
                comp_file.write(navbar_match.group(0))
    
    if topbar_pattern.search(content):
        content = topbar_pattern.sub('<div id="topbar-placeholder"></div>', content)
        modified = True
        
    if navbar_pattern.search(content):
        content = navbar_pattern.sub('<div id="navbar-placeholder"></div>', content)
        modified = True
    elif file == 'mantenimiento_productos.html' and modified:
        content = content.replace('<div id="topbar-placeholder"></div>', '<div id="topbar-placeholder"></div>\n    <div id="navbar-placeholder"></div>')
        modified = True

    if 'load_components.js' not in content:
        content = content.replace('</body>', '    <script src="js/load_components.js"></script>\n</body>')
        modified = True

    if modified:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {file}")

print("Done")
