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
THEMES_DIR = 'themes'
BASE_TEMPLATE = 'base.html'

def get_meta(md_instance, key, default=None):
    if key in md_instance.Meta:
        return md_instance.Meta[key][0]
    return default

class ThemeManager:
    def __init__(self):
        self.envs = {}

    def get_template(self, theme):
        if theme not in self.envs:
            theme_path = os.path.join(THEMES_DIR, theme, 'templates')
            if not os.path.exists(theme_path):
                theme_path = os.path.join(THEMES_DIR, 'default', 'templates')
                theme = 'default'
            self.envs[theme] = Environment(loader=FileSystemLoader(theme_path))
        
        return self.envs[theme].get_template(BASE_TEMPLATE), theme

def resolve_config(path, root_dir):
    """Recursively resolve configuration by looking for .md-server files from current folder up to root."""
    config = {'sitemap': True} # Default sitemap to True
    parts = os.path.relpath(path, root_dir).split(os.sep)
    if parts == ['.']:
        parts = []
    
    current_check = root_dir
    for part in [""] + parts:
        current_check = os.path.join(current_check, part)
        config_file = os.path.join(current_check, '.md-server')
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                new_config = yaml.safe_load(f) or {}
                config.update(new_config)
    return config

def generate_sitemap(output_dir, urls):
    if not urls:
        return
    
    now = datetime.now().strftime('%Y-%m-%d')
    sitemap_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap_content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    
    for url in sorted(urls):
        sitemap_content += f'  <url>\n    <loc>{url}</loc>\n    <lastmod>{now}</lastmod>\n  </url>\n'
    
    sitemap_content += '</urlset>'
    
    with open(os.path.join(output_dir, 'sitemap.xml'), 'w', encoding='utf-8') as f:
        f.write(sitemap_content)
    print(f"Generated sitemap.xml with {len(urls)} URLs")

def generate_site(output_dir='dist', minify=False, default_theme='default'):
    theme_manager = ThemeManager()
    sitemap_urls = []

    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    # First pass: identify blog folders and themes
    blog_configs = {}
    used_themes = set()
    used_themes.add(default_theme)

    for root, dirs, files in os.walk(CONTENT_DIR):
        config = resolve_config(root, CONTENT_DIR)
        theme = config.get('theme', default_theme)
        used_themes.add(theme)
        
        if config.get('type') == 'blog':
            rel_root = os.path.relpath(root, CONTENT_DIR)
            blog_configs[rel_root] = config

    all_posts = {} # rel_root -> list of post metadata and content

    # Second pass: Process all files
    for root, dirs, files in os.walk(CONTENT_DIR):
        rel_root = os.path.relpath(root, CONTENT_DIR)
        config = resolve_config(root, CONTENT_DIR)
        theme_name = config.get('theme', default_theme)
        show_in_sitemap = config.get('sitemap', True)
        
        blog_root = None
        for br in blog_configs:
            if rel_root == br or rel_root.startswith(br + os.sep):
                blog_root = br
                break
        
        is_blog = blog_root is not None
        
        for file in files:
            if file.endswith('.md'):
                md_path = os.path.join(root, file)
                rel_file_path = os.path.relpath(md_path, CONTENT_DIR)
                name_without_ext = os.path.splitext(rel_file_path)[0]
                
                if name_without_ext == 'index':
                    output_file_path = os.path.join(output_dir, 'index.html')
                    url = '/'
                else:
                    output_file_path = os.path.join(output_dir, name_without_ext, 'index.html')
                    url = f'/{name_without_ext}/'
                
                os.makedirs(os.path.dirname(output_file_path), exist_ok=True)

                if show_in_sitemap:
                    sitemap_urls.append(url)

                with open(md_path, 'r', encoding='utf-8') as f:
                    content_md = f.read()
                
                md = markdown.Markdown(extensions=['extra', 'toc', 'codehilite', 'meta', 'sane_lists', 'markdown_checklist.extension'])
                html_body = md.convert(content_md)
                
                title = get_meta(md, 'title', name_without_ext.replace('-', ' ').title())
                author = get_meta(md, 'author', 'Anonymous')
                
                date_str = get_meta(md, 'date')
                if date_str:
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    except ValueError:
                        date_obj = datetime.fromtimestamp(os.path.getmtime(md_path))
                else:
                    date_obj = datetime.fromtimestamp(os.path.getmtime(md_path))

                post_meta = {
                    'title': title,
                    'author': author,
                    'date': date_obj,
                    'url': url,
                    'rel_path': rel_file_path,
                    'content_html': html_body
                }

                if is_blog and file != 'index.md':
                    if blog_root not in all_posts:
                        all_posts[blog_root] = []
                    all_posts[blog_root].append(post_meta)

                template, resolved_theme = theme_manager.get_template(theme_name)
                html_output = template.render(
                    content=html_body,
                    title=title,
                    meta=post_meta,
                    is_blog_post=is_blog,
                    theme=resolved_theme
                )

                if minify:
                    html_output = minify_html.minify(html_output, minify_js=True, minify_css=True)

                with open(output_file_path, 'w', encoding='utf-8') as f:
                    f.write(html_output)
                
                print(f"Generated: {output_file_path} (Theme: {resolved_theme})")

    # Third pass: Generate Paginated Blog Indices
    for rel_root, config in blog_configs.items():
        posts = all_posts.get(rel_root, [])
        posts.sort(key=lambda x: x['date'], reverse=True)
        
        ppp = config.get('posts_per_page', 5)
        total_pages = math.ceil(len(posts) / ppp) or 1
        
        theme_name = config.get('theme', default_theme)
        template, resolved_theme = theme_manager.get_template(theme_name)
        show_in_sitemap = config.get('sitemap', True)

        for i in range(total_pages):
            page_num = i + 1
            start = i * ppp
            end = start + ppp
            page_posts = posts[start:end]
            
            pagination = {
                'current': page_num,
                'total': total_pages,
                'next': None,
                'prev': None
            }
            
            base_blog_url = f"/{rel_root}/"
            if page_num < total_pages:
                pagination['next'] = f"{base_blog_url}page/{page_num + 1}/"
            
            if page_num > 1:
                if page_num == 2:
                    pagination['prev'] = base_blog_url
                else:
                    pagination['prev'] = f"{base_blog_url}page/{page_num - 1}/"

            if show_in_sitemap:
                if page_num == 1:
                    sitemap_urls.append(base_blog_url)
                else:
                    sitemap_urls.append(f"{base_blog_url}page/{page_num}/")

            page_html = ""
            for p in page_posts:
                date_fmt = p['date'].strftime('%Y-%m-%d')
                page_html += f"""
                <article class="blog-post">
                    <header>
                        <h1><a href="{p['url']}">{p['title']}</a></h1>
                        <p class="post-meta">Published on {date_fmt} by {p['author']}</p>
                    </header>
                    <div class="post-content">
                        {p['content_html']}
                    </div>
                </article>
                """

            if page_num == 1:
                output_index_path = os.path.join(output_dir, rel_root, 'index.html')
            else:
                output_index_path = os.path.join(output_dir, rel_root, 'page', str(page_num), 'index.html')
            
            os.makedirs(os.path.dirname(output_index_path), exist_ok=True)
            
            html_output = template.render(
                content=page_html,
                title=f"{rel_root.title()} - Page {page_num}",
                pagination=pagination,
                theme=resolved_theme
            )
            
            if minify:
                html_output = minify_html.minify(html_output, minify_js=True, minify_css=True)
            
            with open(output_index_path, 'w', encoding='utf-8') as f:
                f.write(html_output)
            print(f"Generated Blog Index: {output_index_path} (Theme: {resolved_theme})")

    # Generate sitemap if enabled at root
    root_config = resolve_config(CONTENT_DIR, CONTENT_DIR)
    if root_config.get('sitemap', True):
        generate_sitemap(output_dir, sitemap_urls)

    # Copy and minify static assets for all used themes
    for theme in used_themes:
        theme_static = os.path.join(THEMES_DIR, theme, 'static')
        if os.path.exists(theme_static):
            target_static = os.path.join(output_dir, 'static', theme)
            shutil.copytree(theme_static, target_static)
            
            if minify:
                for root, dirs, files in os.walk(target_static):
                    for file in files:
                        if file.endswith('.css'):
                            path = os.path.join(root, file)
                            with open(path, 'r') as f:
                                minified = compress(f.read())
                            with open(path, 'w') as f:
                                f.write(minified)
            print(f"Copied static assets for theme: {theme}")

def find_available_port(start_port=8000):
    port = start_port
    while port < start_port + 100:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('', port)) != 0:
                return port
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
            if s.connect_ex(('', port)) != 0:
                return port
        port += 1
    return start_port

DIRECTORY = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

if __name__ == "__main__":
    PORT = find_available_port(8000)
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Serving build at http://localhost:{{PORT}}")
        httpd.serve_forever()
"""
    with open(os.path.join(output_dir, 'server.py'), 'w', encoding='utf-8') as f:
        f.write(server_script)
    print(f"Created {output_dir}/server.py for deployment.")

class ChangeHandler(FileSystemEventHandler):
    def __init__(self, default_theme):
        self.default_theme = default_theme
    def on_any_event(self, event):
        if event.is_directory:
            return
        if any(event.src_path.endswith(ext) for ext in ['.md', '.html', '.css', '.md-server']):
            print(f"Change detected: {event.src_path}. Regenerating...")
            generate_site('dist', default_theme=self.default_theme)

def serve_dev(directory, port=8000):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)
    with http.server.HTTPServer(("", port), Handler) as httpd:
        print(f"Dev server running at http://localhost:{port}")
        httpd.serve_forever()

def main():
    parser = argparse.ArgumentParser(description='Markdown Website Generator')
    parser.add_argument('-dev', action='store_true', help='Development mode with hot-reloading')
    parser.add_argument('-build', action='store_true', help='Build for deployment in /build with minification')
    parser.add_argument('--theme', default='default', help='Global default theme (default: "default")')
    args = parser.parse_args()

    if args.build:
        print(f"Building site for deployment with default theme '{args.theme}'...")
        generate_site('build', minify=True, default_theme=args.theme)
        create_build_server('build')
    elif args.dev:
        print(f"Starting development mode with default theme '{args.theme}'...")
        generate_site('dist', minify=False, default_theme=args.theme)
        
        port = find_available_port(8000)
        server_thread = threading.Thread(target=serve_dev, args=('dist', port), daemon=True)
        server_thread.start()

        event_handler = ChangeHandler(args.theme)
        observer = Observer()
        observer.schedule(event_handler, CONTENT_DIR, recursive=True)
        observer.schedule(event_handler, THEMES_DIR, recursive=True)
        
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
    else:
        generate_site('dist', default_theme=args.theme)

if __name__ == "__main__":
    main()
