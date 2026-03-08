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
BASE_TEMPLATE = 'base.html'

def get_meta(md_instance, key, default=None):
    if key in md_instance.Meta:
        return md_instance.Meta[key][0]
    return default

def generate_site(output_dir='dist', minify=False):
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    template = env.get_template(BASE_TEMPLATE)

    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    # First pass: identify blog folders
    blog_configs = {}
    for root, dirs, files in os.walk(CONTENT_DIR):
        if '.md-server' in files:
            config_path = os.path.join(root, '.md-server')
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
                if config.get('type') == 'blog':
                    rel_root = os.path.relpath(root, CONTENT_DIR)
                    blog_configs[rel_root] = config

    all_posts = {} # rel_root -> list of post metadata and content

    # Second pass: Process all files
    for root, dirs, files in os.walk(CONTENT_DIR):
        rel_root = os.path.relpath(root, CONTENT_DIR)
        
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

                with open(md_path, 'r', encoding='utf-8') as f:
                    content_md = f.read()
                
                md = markdown.Markdown(extensions=['extra', 'toc', 'codehilite', 'meta', 'sane_lists'])
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

                html_output = template.render(
                    content=html_body,
                    title=title,
                    meta=post_meta,
                    is_blog_post=is_blog
                )

                if minify:
                    html_output = minify_html.minify(html_output, minify_js=True, minify_css=True)

                with open(output_file_path, 'w', encoding='utf-8') as f:
                    f.write(html_output)
                
                print(f"Generated: {output_file_path}")

    # Third pass: Generate Paginated Blog Indices
    for rel_root, config in blog_configs.items():
        posts = all_posts.get(rel_root, [])
        posts.sort(key=lambda x: x['date'], reverse=True)
        
        ppp = config.get('posts_per_page', 5)
        total_pages = math.ceil(len(posts) / ppp) or 1
        
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
                pagination=pagination
            )
            
            if minify:
                html_output = minify_html.minify(html_output, minify_js=True, minify_css=True)
            
            with open(output_index_path, 'w', encoding='utf-8') as f:
                f.write(html_output)
            print(f"Generated Blog Index: {output_index_path}")

    # Copy and minify static assets
    if os.path.exists(STATIC_DIR):
        target_static = os.path.join(output_dir, 'static')
        shutil.copytree(STATIC_DIR, target_static)
        
        if minify:
            for root, dirs, files in os.walk(target_static):
                for file in files:
                    if file.endswith('.css'):
                        path = os.path.join(root, file)
                        with open(path, 'r') as f:
                            minified = compress(f.read())
                        with open(path, 'w') as f:
                            f.write(minified)
                        print(f"Minified CSS: {path}")

        print(f"Copied {STATIC_DIR} to {output_dir}/static")

def find_available_port(start_port=8000):
    port = start_port
    while port < start_port + 100:
        with socket.socket(socket.socket.AF_INET, socket.SOCK_STREAM) as s:
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
        with socket.socket(socket.socket.AF_INET, socket.SOCK_STREAM) as s:
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
    def on_any_event(self, event):
        if event.is_directory:
            return
        if any(event.src_path.endswith(ext) for ext in ['.md', '.html', '.css', '.md-server']):
            print(f"Change detected: {event.src_path}. Regenerating...")
            generate_site('dist')

def serve_dev(directory, port=8000):
    os.chdir(directory)
    handler = http.server.SimpleHTTPRequestHandler
    with http.server.HTTPServer(("", port), handler) as httpd:
        print(f"Dev server running at http://localhost:{port}")
        httpd.serve_forever()

def main():
    parser = argparse.ArgumentParser(description='Markdown Website Generator')
    parser.add_argument('-dev', action='store_true', help='Development mode with hot-reloading')
    parser.add_argument('-build', action='store_true', help='Build for deployment in /build with minification')
    args = parser.parse_args()

    if args.build:
        print("Building site for deployment with minification...")
        generate_site('build', minify=True)
        create_build_server('build')
    elif args.dev:
        print("Starting development mode...")
        generate_site('dist', minify=False)
        
        port = find_available_port(8000)
        server_thread = threading.Thread(target=serve_dev, args=('dist', port), daemon=True)
        server_thread.start()

        event_handler = ChangeHandler()
        observer = Observer()
        for d in [CONTENT_DIR, TEMPLATES_DIR, STATIC_DIR]:
            if os.path.exists(d):
                observer.schedule(event_handler, d, recursive=True)
        
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
    else:
        generate_site('dist')

if __name__ == "__main__":
    main()
