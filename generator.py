import os
import shutil
import markdown
import argparse
import time
import http.server
import threading
import yaml
import socket
import math
import minify_html
from csscompressor import compress
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuration
CONTENT_DIR = 'content'
TEMPLATES_DIR = 'templates'
STATIC_DIR = 'static'

def get_meta(md_instance, key, default=None):
    if key in md_instance.Meta:
        return md_instance.Meta[key][0]
    return default

def resolve_config(path, root_dir):
    """Recursively resolve configuration by looking for .md-server files from current folder up to root."""
    # Start with global defaults
    config = {'sitemap': True, 'theme': 'default', 'template': 'page'}
    
    # Get path relative to root_dir
    rel_path = os.path.relpath(path, root_dir)
    parts = [] if rel_path == '.' else rel_path.split(os.sep)
    
    # Iterate from root down to the target folder
    current_check = root_dir
    path_to_check = [root_dir]
    for part in parts:
        current_check = os.path.join(current_check, part)
        path_to_check.append(current_check)
        
    for folder in path_to_check:
        config_file = os.path.join(folder, '.md-server')
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                new_config = yaml.safe_load(f) or {}
                config.update(new_config)
    
    return config

def generate_sitemap(output_dir, urls):
    if not urls:
        return
    now = datetime.now().strftime('%Y-%m-%d')
    sitemap_content = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for url in sorted(urls):
        sitemap_content += f'  <url>\n    <loc>{url}</loc>\n    <lastmod>{now}</lastmod>\n  </url>\n'
    sitemap_content += '</urlset>'
    with open(os.path.join(output_dir, 'sitemap.xml'), 'w', encoding='utf-8') as f:
        f.write(sitemap_content)
    print(f"Generated sitemap.xml with {len(urls)} URLs")

def generate_site(output_dir='dist', minify=False):
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    sitemap_urls = []

    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    # First pass: identify blog folders
    blog_configs = {}
    for root, dirs, files in os.walk(CONTENT_DIR):
        config = resolve_config(root, CONTENT_DIR)
        if config.get('type') == 'blog':
            rel_root = os.path.relpath(root, CONTENT_DIR)
            blog_configs[rel_root] = config

    all_posts = {} # rel_root -> list of post metadata and content

    # Second pass: Process all files
    for root, dirs, files in os.walk(CONTENT_DIR):
        rel_root = os.path.relpath(root, CONTENT_DIR)
        config = resolve_config(root, CONTENT_DIR)
        
        theme_name = config.get('theme', 'default')
        
        # Determine if we are in a blog context
        blog_root = None
        for br in blog_configs:
            if rel_root == br or rel_root.startswith(br + os.sep):
                blog_root = br
                break
        
        is_blog_section = blog_root is not None
        
        for file in files:
            if file.endswith('.md'):
                md_path = os.path.join(root, file)
                rel_file_path = os.path.relpath(md_path, CONTENT_DIR)
                name_without_ext = os.path.splitext(rel_file_path)[0]
                
                # Output Path
                if name_without_ext == 'index':
                    output_file_path = os.path.join(output_dir, 'index.html')
                    url = '/'
                else:
                    output_file_path = os.path.join(output_dir, name_without_ext, 'index.html')
                    url = f'/{name_without_ext}/'
                
                os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
                if config.get('sitemap', True):
                    sitemap_urls.append(url)

                # Convert Markdown
                with open(md_path, 'r', encoding='utf-8') as f:
                    content_md = f.read()
                
                md = markdown.Markdown(extensions=['extra', 'toc', 'codehilite', 'meta', 'sane_lists', 'markdown_checklist.extension'])
                html_body = md.convert(content_md)
                
                # Meta
                title = get_meta(md, 'title', name_without_ext.replace('-', ' ').title())
                author = get_meta(md, 'author', 'Anonymous')
                date_str = get_meta(md, 'date')
                date_obj = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.fromtimestamp(os.path.getmtime(md_path))

                post_meta = {'title': title, 'author': author, 'date': date_obj, 'url': url, 'content_html': html_body}

                # Template selection
                if is_blog_section and file != 'index.md':
                    if blog_root not in all_posts:
                        all_posts[blog_root] = []
                    all_posts[blog_root].append(post_meta)
                    # For posts, look for post_template, otherwise use blog_post
                    template_to_use = config.get('post_template', 'blog_post')
                else:
                    # For regular pages, use 'template' setting
                    template_to_use = config.get('template', 'page')
                
                if not template_to_use.endswith('.html'):
                    template_to_use += '.html'

                # Render
                tpl = env.get_template(template_to_use)
                html_output = tpl.render(
                    content=html_body,
                    title=title,
                    meta=post_meta,
                    theme=theme_name
                )

                if minify:
                    html_output = minify_html.minify(html_output, minify_js=True, minify_css=True)

                with open(output_file_path, 'w', encoding='utf-8') as f:
                    f.write(html_output)
                print(f"Generated: {output_file_path} (Theme: {theme_name}, Template: {template_to_use})")

    # Third pass: Blog Indices
    for rel_root, config in blog_configs.items():
        posts = sorted(all_posts.get(rel_root, []), key=lambda x: x['date'], reverse=True)
        ppp = config.get('posts_per_page', 5)
        total_pages = math.ceil(len(posts) / ppp) or 1
        
        theme_name = config.get('theme', 'default')
        # For index pages, if template is still 'page', override with 'blog_index'
        template_to_use = config.get('template')
        if template_to_use == 'page' or template_to_use is None:
            template_to_use = 'blog_index'
            
        if not template_to_use.endswith('.html'):
            template_to_use += '.html'

        for i in range(total_pages):
            page_num = i + 1
            page_posts = posts[i * ppp : (i + 1) * ppp]
            
            pagination = {'current': page_num, 'total': total_pages, 'next': None, 'prev': None}
            base_blog_url = f"/{rel_root}/"
            if page_num < total_pages: pagination['next'] = f"{base_blog_url}page/{page_num + 1}/"
            if page_num > 1: pagination['prev'] = base_blog_url if page_num == 2 else f"{base_blog_url}page/{page_num - 1}/"

            if config.get('sitemap', True):
                sitemap_urls.append(base_blog_url if page_num == 1 else f"{base_blog_url}page/{page_num}/")

            page_html = ""
            for p in page_posts:
                date_fmt = p['date'].strftime('%Y-%m-%d')
                page_html += f"""
                <article class="blog-post">
                    <header>
                        <h1><a href="{p['url']}">{p['title']}</a></h1>
                        <p class="post-meta">Published on {date_fmt} by {p['author']}</p>
                    </header>
                    <div class="post-content">{p['content_html']}</div>
                </article>"""

            out_path = os.path.join(output_dir, rel_root, 'index.html') if page_num == 1 else os.path.join(output_dir, rel_root, 'page', str(page_num), 'index.html')
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            
            tpl = env.get_template(template_to_use)
            html_output = tpl.render(content=page_html, title=f"{rel_root.title()} - Page {page_num}", pagination=pagination, theme=theme_name)
            
            if minify: html_output = minify_html.minify(html_output, minify_js=True, minify_css=True)
            with open(out_path, 'w', encoding='utf-8') as f: f.write(html_output)
            print(f"Generated Blog Index: {out_path} (Theme: {theme_name}, Template: {template_to_use})")

    # Sitemap
    if resolve_config(CONTENT_DIR, CONTENT_DIR).get('sitemap', True):
        generate_sitemap(output_dir, sitemap_urls)

    # Static Assets
    if os.path.exists(STATIC_DIR):
        target_static = os.path.join(output_dir, 'static')
        shutil.copytree(STATIC_DIR, target_static)
        
        if minify:
            for root, dirs, files in os.walk(target_static):
                for file in files:
                    if file.endswith('.css'):
                        path = os.path.join(root, file)
                        with open(path, 'r') as f: minified = compress(f.read())
                        with open(path, 'w') as f: f.write(minified)
        print(f"Copied static assets and minified CSS.")

def find_available_port(start_port=8000):
    port = start_port
    while port < start_port + 100:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('', port)) != 0: return port
        port += 1
    return start_port

def create_build_server(output_dir):
    server_script = f"""
import http.server
import socketserver
import os
import socket

def find_available_port(start_port=8000):
    port = start_port
    while port < start_port + 100:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('', port)) != 0: return port
        port += 1
    return start_port

DIRECTORY = os.path.dirname(os.path.abspath(__file__))
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs): super().__init__(*args, directory=DIRECTORY, **kwargs)

if __name__ == "__main__":
    PORT = find_available_port(8000)
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Serving build at http://localhost:{{PORT}}")
        httpd.serve_forever()
"""
    with open(os.path.join(output_dir, 'server.py'), 'w', encoding='utf-8') as f: f.write(server_script)
    print(f"Created {output_dir}/server.py for deployment.")

class ChangeHandler(FileSystemEventHandler):
    def __init__(self):
        self.last_trigger = 0

    def on_any_event(self, event):
        if event.is_directory: return
        
        if time.time() - self.last_trigger < 0.5: return

        abs_path = os.path.abspath(event.src_path)
        if '/dist/' in abs_path or '/build/' in abs_path: return

        if any(abs_path.endswith(ext) for ext in ['.md', '.html', '.css', '.md-server']):
            print(f"Change detected: {event.src_path}. Regenerating...")
            self.last_trigger = time.time()
            generate_site('dist')

def serve_dev(directory, port=8000):
    os.chdir(directory)
    with http.server.HTTPServer(("", port), http.server.SimpleHTTPRequestHandler) as httpd:
        print(f"Dev server running at http://localhost:{port}"); httpd.serve_forever()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-dev', action='store_true')
    parser.add_argument('-build', action='store_true')
    args = parser.parse_args()

    if args.build:
        generate_site('build', minify=True)
        create_build_server('build')
    elif args.dev:
        generate_site('dist')
        port = find_available_port(8000)
        threading.Thread(target=serve_dev, args=('dist', port), daemon=True).start()
        
        handler = ChangeHandler()
        observer = Observer()
        for d in [CONTENT_DIR, TEMPLATES_DIR, STATIC_DIR]:
            if os.path.exists(d):
                observer.schedule(handler, os.path.abspath(d), recursive=True)
        
        observer.start()
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt: observer.stop()
        observer.join()
    else:
        generate_site('dist')

if __name__ == "__main__":
    main()
