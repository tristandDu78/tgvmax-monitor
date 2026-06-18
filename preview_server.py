"""Serveur de preview local — sert index.html depuis la racine du projet."""
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.path = '/index.html'
        return super().do_GET()
    def log_message(self, *_):
        pass

os.chdir(os.path.dirname(os.path.abspath(__file__)))
print("Preview sur http://localhost:3000  (Ctrl+C pour arrêter)")
HTTPServer(('', 3000), Handler).serve_forever()
