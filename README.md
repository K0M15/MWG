# Markdown Website Generator

A simple, powerful, and flexible static site generator (SSG) built with Python. Convert your Markdown files into a modern website with clean URLs, hot-reloading, and built-in blogging support.

## 🚀 Features

- **Pure Markdown**: Write content in GitHub-Flavored Markdown (GFM).
- **Clean URLs**: Automatic directory-based routing (e.g., `about.md` becomes `/about/index.html`).
- **Dev Mode**: Local server with **hot-reloading** on any file change.
- **Build Mode**: Generates a production-ready `/build` folder with a standalone `server.py` for easy deployment.
- **Blogging Engine**: 
    - Enable blogging per folder via `.md-server` config.
    - Automatic paginated index pages with full post content.
    - Metadata support (Title, Author, Date) with intelligent fallbacks.
- **Syntax Highlighting**: Built-in support for code blocks via Pygments.
- **Automatic Port Discovery**: Finds the next available port if `8000` is taken.

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
Start the dev server. It will watch for changes in `content/`, `templates/`, and `static/`.
```bash
./venv/bin/python generator.py -dev
```

### Production Build
Generate the final website in the `/build` directory.
```bash
./venv/bin/python generator.py -build
```

### Deployment
To test your production build locally:
```bash
python3 build/server.py
```

## 📂 Project Structure

- **`content/`**: Your Markdown (`.md`) files.
    - `index.md` -> `/index.html`
    - `about.md` -> `/about/index.html`
    - `blog/` -> Any folder can be a blog (see below).
- **`templates/`**: HTML templates using **Jinja2**.
    - `base.html`: The main layout for all pages.
- **`static/`**: Static assets (CSS, JS, images).
- **`dist/`**: Temporary output folder used during `-dev` mode.
- **`build/`**: Final production output folder.
- **`generator.py`**: The core Python script.

## 📝 Blogging Configuration

To turn a folder into a blog, create a `.md-server` file inside that folder:

```yaml
# content/blog/.md-server
type: blog
posts_per_page: 5
```

### Post Metadata
Add a header to your `.md` files to provide metadata:

```markdown
title: My Great Post
author: Alain
date: 2024-03-08

# Content starts here...
```
*Note: If `date` is missing, the file's last modified time is used.*

## 🎨 Markdown Flavor
The generator supports **GitHub-Flavored Markdown**, including:
- Tables
- Fenced code blocks with syntax highlighting
- Task lists
- Table of Contents (use `[TOC]`)
- Admonitions
