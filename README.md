# Markdown Website Generator

A simple, powerful, and flexible static site generator (SSG) built with Python. Convert your Markdown files into a modern website with clean URLs, hot-reloading, and built-in blogging support.

## 🚀 Features

- **Pure Markdown**: Write content in GitHub-Flavored Markdown (GFM).
- **Clean URLs**: Automatic directory-based routing (e.g., `about.md` becomes `/about/index.html`).
- **Dev Mode**: Local server with **hot-reloading** on any file change.
- **Build Mode**: Generates a production-ready `/build` folder with a standalone `server.py` and minified assets.
- **Blogging Engine**: 
    - Enable blogging per folder via `.md-server` config.
    - Automatic paginated index pages with full post content.
    - Metadata support (Title, Author, Date) with intelligent fallbacks.
- **Syntax Highlighting**: Built-in support for code blocks via Pygments.
- **Automatic Sitemap**: Generates a standard `sitemap.xml` for all pages.
- **Themes & Templates**: Independent control over visual styles and HTML structure.

## 🛠️ Installation

1. **Clone or create the project directory.**
2. **Create a virtual environment:**
   ```bash
   python3 -m venv venv
   ```
3. **Install dependencies:**
   ```bash
   ./venv/bin/pip install -r requirements.txt
   ```

## 📖 Usage

### Development (Hot-Reloading)
Start the dev server. It watches `content/`, `templates/`, and `static/`.
```bash
./venv/bin/python generator.py -dev
```

### Production Build
Generates the final website in the `/build` directory with minification.
```bash
./venv/bin/python generator.py -build
```

### Deployment
Test your production build locally:
```bash
python3 build/server.py
```

## 📂 Project Structure

- **`content/`**: Your Markdown (`.md`) files and `.md-server` configs.
- **`templates/`**: HTML templates (`base.html`, `page.html`, `blog_post.html`, etc.).
- **`static/themes/`**: CSS theme directories (e.g., `default`, `matrix`).
- **`generator.py`**: The core Python script.

## 📝 Configuration (`.md-server`)

Settings are managed via `.md-server` YAML files in your `content/` folders. Settings are **hierarchical**: a folder inherits settings from its parent unless overridden.

### Available Keys:
| Key | Description | Default |
| :--- | :--- | :--- |
| `theme` | The CSS theme to use (folder in `static/themes/`). | `default` |
| `template` | The HTML template to use (file in `templates/`). | `page` |
| `type` | Set to `blog` to enable blogging features for a folder. | `None` |
| `posts_per_page`| Number of posts shown on each blog index page. | `5` |
| `sitemap` | Set to `false` to exclude a folder from `sitemap.xml`. | `true` |

**Example:**
```yaml
# content/blog/.md-server
theme: matrix
type: blog
posts_per_page: 3
```

## 🎨 Themes & Templates

### Themes
Themes are strictly CSS-based and stored in `static/themes/<theme-name>/style.css`.
Available themes:
- `default`: Clean and simple light theme.
- `dark-mode`: Dark gray modern theme.
- `matrix`: Classic black & green hacker aesthetic.
- `colorful`: Vibrant, playful, and colorful.

### Templates
Templates are stored in the `templates/` directory.
- `page.html`: Default for standard pages.
- `blog_index.html`: Default for blog listing pages.
- `blog_post.html`: Default for individual blog entries.

## ✍️ Post Metadata

Add a YAML header to your `.md` files to provide metadata:

```markdown
title: My Great Post
author: Alain
date: 2024-03-08

# Content starts here...
```
*Note: If `date` is missing, the file's last modified time is used.*
