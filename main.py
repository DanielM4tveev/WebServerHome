from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
import json
import os
import mimetypes

class FileRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed_path = urlparse(self.path)
            
            if parsed_path.path.startswith('/download'):
                self.handle_download(parsed_path)
            elif parsed_path.path == '/files':
                self.handle_files_request(parsed_path)
            elif parsed_path.path == '/':
                self.send_index_page()
            else:
                self.handle_file_request(parsed_path.path)
        except Exception as e:
            self.send_error(500, f"Server error: {str(e)}")
    
    def handle_file_request(self, path):
        # Remove leading slash and decode URL encoding
        filepath = unquote(path[1:])
        
        if not os.path.exists(filepath):
            self.send_error(404, "File not found")
            return
        
        if not self.is_safe_path(filepath):
            self.send_error(403, "Forbidden")
            return
        
        if os.path.isdir(filepath):
            self.send_error(403, "Directory listing not allowed")
            return
        
        content_type = self.guess_content_type(filepath)
        try:
            with open(filepath, 'rb') as f:
                self.send_response(200)
                self.send_header('Content-type', content_type)
                
                # For media files allow byte ranges
                if content_type.startswith(('audio/', 'video/', 'image/')):
                    self.send_header('Accept-Ranges', 'bytes')
                
                self.end_headers()
                
                # Stream the file in chunks
                chunk_size = 8192
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except Exception as e:
            self.send_error(500, f"Error reading file: {str(e)}")
    
    def handle_download(self, parsed_path):
        query = parse_qs(parsed_path.query)
        filepath = unquote(query.get('file', [None])[0])
        
        if not filepath or not os.path.exists(filepath):
            self.send_error(404, "File not found")
            return
        
        if not self.is_safe_path(filepath):
            self.send_error(403, "Forbidden")
            return
        
        filename = os.path.basename(filepath)
        try:
            with open(filepath, 'rb') as f:
                self.send_response(200)
                self.send_header('Content-type', 'application/octet-stream')
                self.send_header('Content-Disposition', 
                               f'attachment; filename="{filename}"')
                self.end_headers()
                
                # Stream the file in chunks
                chunk_size = 8192
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except Exception as e:
            self.send_error(500, f"Error reading file: {str(e)}")
    
    def handle_files_request(self, parsed_path):
        query = parse_qs(parsed_path.query)
        path = query.get('path', [None])[0]
        search = query.get('search', [None])[0]
        is_root = query.get('root', ['false'])[0].lower() == 'true'
        
        if search:
            files = self.search_files(os.getcwd(), search)
        elif is_root:
            files = self.list_files(os.getcwd(), recursive=False)
        elif path:
            path = unquote(path)
            if not os.path.exists(path):
                self.send_error(404, "Path not found")
                return
            files = self.list_files(path, recursive=False)
        else:
            self.send_error(400, "Bad request")
            return
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(files).encode())
    
    def send_index_page(self):
        try:
            with open('index.html', 'rb') as f:
                content = f.read()
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, "index.html not found")
    
    def list_files(self, dir_path, recursive=False):
        files = []
        
        try:
            items = os.listdir(dir_path)
        except PermissionError:
            return files
            
        for item in items:
            if item.startswith('.'):
                continue
                
            full_path = os.path.join(dir_path, item)
            rel_path = os.path.relpath(full_path, os.getcwd())
            
            try:
                if os.path.isdir(full_path):
                    file_info = {
                        'name': item,
                        'path': full_path.replace('\\', '/'),
                        'is_directory': True,
                        'size': 0,
                        'modified': os.path.getmtime(full_path)
                    }
                    files.append(file_info)
                    
                    if recursive:
                        files.extend(self.list_files(full_path, recursive))
                else:
                    if item in ['main.py', 'index.html']:
                        continue
                        
                    file_info = {
                        'name': item,
                        'path': rel_path.replace('\\', '/'),
                        'is_directory': False,
                        'size': os.path.getsize(full_path),
                        'modified': os.path.getmtime(full_path)
                    }
                    files.append(file_info)
            except (PermissionError, OSError):
                continue
        
        files.sort(key=lambda x: (not x['is_directory'], x['name'].lower()))
        return files
    
    def search_files(self, root_dir, search_term):
        results = []
        search_term = search_term.lower()
        
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            
            for name in dirnames + filenames:
                if name.lower().find(search_term) != -1:
                    full_path = os.path.join(dirpath, name)
                    rel_path = os.path.relpath(full_path, os.getcwd())
                    
                    try:
                        if os.path.isdir(full_path):
                            file_info = {
                                'name': name,
                                'path': full_path.replace('\\', '/'),
                                'is_directory': True,
                                'size': 0,
                                'modified': os.path.getmtime(full_path)
                            }
                        else:
                            if name in ['main.py', 'index.html']:
                                continue
                                
                            file_info = {
                                'name': name,
                                'path': rel_path.replace('\\', '/'),
                                'is_directory': False,
                                'size': os.path.getsize(full_path),
                                'modified': os.path.getmtime(full_path)
                            }
                        results.append(file_info)
                    except (PermissionError, OSError):
                        continue
        
        return results
    
    def guess_content_type(self, filename):
        # Use mimetypes first, then fallback to our custom types
        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type:
            return mime_type
        
        extension = filename.split('.')[-1].lower()
        custom_types = {
            'md': 'text/markdown',
            'webp': 'image/webp',
            'webm': 'video/webm',
            'ogg': 'audio/ogg',
            'csv': 'text/csv',
            'svg': 'image/svg+xml'
        }
        return custom_types.get(extension, 'application/octet-stream')
    
    def is_safe_path(self, path):
        # Prevent directory traversal
        root = os.path.abspath(os.getcwd())
        requested_path = os.path.abspath(os.path.join(root, path))
        return requested_path.startswith(root)

def run_server(port=8000):
    # Configure mimetypes
    mimetypes.add_type('text/markdown', '.md')
    mimetypes.add_type('application/javascript', '.js')
    mimetypes.add_type('text/css', '.css')
    
    server_address = ('', port)
    httpd = HTTPServer(server_address, FileRequestHandler)
    print(f'Starting server on port {port}...')
    httpd.serve_forever()

if __name__ == '__main__':
    run_server()
