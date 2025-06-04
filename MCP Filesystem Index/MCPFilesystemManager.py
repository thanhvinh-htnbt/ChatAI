import asyncio
import json
import hashlib
import os
import warnings
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Suppress all ResourceWarnings on Windows
if os.name == 'nt':
    warnings.filterwarnings("ignore", category=ResourceWarning)
    # Also suppress asyncio debug warnings
    import logging

    logging.getLogger('asyncio').setLevel(logging.ERROR)


class MCPFilesystemManager:
    """MCP Filesystem Manager with indexing and metadata capabilities for offline use"""

    def __init__(self, base_directory: str, index_file: str = ".mcp_index.json"):
        self.base_directory = Path(base_directory).resolve()
        self.index_file = self.base_directory / index_file
        self.metadata_cache = {}
        self.file_index = {}

        # MCP Server parameters - Using mcp-server-filesystem directly
        self.server_params = StdioServerParameters(
            command="mcp-server-filesystem",
            args=[str(self.base_directory)]
        )

        # Load existing index
        self._load_index()

    async def __aenter__(self):
        """Async context manager entry"""
        try:
            self.stdio_client = stdio_client(self.server_params)
            self.read, self.write = await self.stdio_client.__aenter__()
            self.session = ClientSession(self.read, self.write)
            await self.session.__aenter__()

            # Initialize MCP session
            result = await self.session.initialize()
            print(f"MCP session initialized: {result}")

            # Refresh file index on startup
            await self.refresh_index()

            return self
        except Exception as e:
            print(f"Error initializing MCP session: {e}")
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        # Save index before closing
        self._save_index()

        # Properly close session and stdio client
        try:
            if hasattr(self, 'session'):
                await self.session.__aexit__(exc_type, exc_val, exc_tb)
        except Exception as e:
            pass  # Ignore cleanup errors

        try:
            if hasattr(self, 'stdio_client'):
                await self.stdio_client.__aexit__(exc_type, exc_val, exc_tb)
        except Exception as e:
            pass  # Ignore cleanup errors

        # Give a moment for cleanup
        await asyncio.sleep(0.1)

    def _load_index(self):
        """Load file index from disk"""
        try:
            if self.index_file.exists():
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.file_index = data.get('file_index', {})
                    self.metadata_cache = data.get('metadata_cache', {})
                print(f"Loaded index with {len(self.file_index)} files")
            else:
                print("No existing index found, will create new one")
        except Exception as e:
            print(f"Error loading index: {e}")
            self.file_index = {}
            self.metadata_cache = {}

    def _save_index(self):
        """Save file index to disk"""
        try:
            index_data = {
                'file_index': self.file_index,
                'metadata_cache': self.metadata_cache,
                'last_updated': datetime.now().isoformat()
            }

            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
            print(f"Index saved with {len(self.file_index)} files")
        except Exception as e:
            print(f"Error saving index: {e}")

    def _calculate_file_hash(self, filepath: Path) -> str:
        """Calculate SHA256 hash of file content"""
        try:
            hasher = hashlib.sha256()
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            print(f"Error calculating hash for {filepath}: {e}")
            return ""

    def _get_file_metadata(self, filepath: Path) -> Dict[str, Any]:
        """Extract file metadata"""
        try:
            stat = filepath.stat()
            return {
                'size': stat.st_size,
                'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'extension': filepath.suffix.lower(),
                'name': filepath.name,
                'path': str(filepath.relative_to(self.base_directory)),
                'hash': self._calculate_file_hash(filepath),
                'indexed_at': datetime.now().isoformat()
            }
        except Exception as e:
            print(f"Error getting metadata for {filepath}: {e}")
            return {}

    async def refresh_index(self):
        """Refresh the file index by scanning the directory"""
        print("Refreshing file index...")
        new_index = {}

        try:
            # Scan all files in directory
            for filepath in self.base_directory.rglob('*'):
                if filepath.is_file() and not filepath.name.startswith('.mcp_'):
                    relative_path = str(filepath.relative_to(self.base_directory))

                    # Get file metadata
                    metadata = self._get_file_metadata(filepath)

                    # Check if file has changed
                    if relative_path in self.file_index:
                        old_hash = self.file_index[relative_path].get('hash', '')
                        if old_hash != metadata.get('hash', ''):
                            print(f"File changed: {relative_path}")
                    else:
                        print(f"New file found: {relative_path}")

                    new_index[relative_path] = metadata

            self.file_index = new_index
            print(f"Index refreshed: {len(self.file_index)} files indexed")

        except Exception as e:
            print(f"Error refreshing index: {e}")

    async def read_file(self, filepath: str) -> Optional[str]:
        """Read file using MCP and update metadata"""
        try:
            # Convert relative path to absolute path within the base directory
            if not os.path.isabs(filepath):
                absolute_path = str(self.base_directory / filepath)
            else:
                absolute_path = filepath

            result = await self.session.call_tool("read_file", {"path": absolute_path})
            content = result.content[0].text if result.content else None

            # Update access time in metadata
            relative_path = str(Path(absolute_path).relative_to(self.base_directory))
            if relative_path in self.file_index:
                self.file_index[relative_path]['last_accessed'] = datetime.now().isoformat()

            return content
        except Exception as e:
            print(f"Error reading file {filepath}: {e}")
            return None

    async def write_file(self, filepath: str, content: str) -> bool:
        """Write file using MCP and update index"""
        try:
            # Convert relative path to absolute path within the base directory
            if not os.path.isabs(filepath):
                absolute_path = str(self.base_directory / filepath)
            else:
                absolute_path = filepath

            result = await self.session.call_tool("write_file", {
                "path": absolute_path,
                "content": content
            })

            # Update index after successful write
            full_path = Path(absolute_path)
            if full_path.exists():
                relative_path = str(full_path.relative_to(self.base_directory))
                self.file_index[relative_path] = self._get_file_metadata(full_path)

            return True
        except Exception as e:
            print(f"Error writing file {filepath}: {e}")
            return False

    async def list_directory(self, path: str = ".") -> List[str]:
        """List directory using MCP"""
        try:
            # Convert relative path to absolute path within the base directory
            if not os.path.isabs(path):
                absolute_path = str(self.base_directory / path)
            else:
                absolute_path = path

            result = await self.session.call_tool("list_directory", {"path": absolute_path})
            return result.content[0].text.split('\n') if result.content else []
        except Exception as e:
            print(f"Error listing directory {path}: {e}")
            return []

    def search_files(self, query: str, search_type: str = "name") -> List[Dict[str, Any]]:
        """Search files in the index"""
        results = []
        query_lower = query.lower()

        for filepath, metadata in self.file_index.items():
            match = False

            if search_type == "name":
                match = query_lower in metadata.get('name', '').lower()
            elif search_type == "extension":
                match = metadata.get('extension', '').lower() == query_lower
            elif search_type == "path":
                match = query_lower in filepath.lower()
            elif search_type == "size":
                try:
                    size_bytes = int(query)
                    match = metadata.get('size', 0) >= size_bytes
                except ValueError:
                    match = False

            if match:
                results.append({
                    'path': filepath,
                    'metadata': metadata
                })

        return results

    def get_file_stats(self) -> Dict[str, Any]:
        """Get statistics about indexed files"""
        if not self.file_index:
            return {}

        total_files = len(self.file_index)
        total_size = sum(meta.get('size', 0) for meta in self.file_index.values())

        # Group by extension
        extensions = {}
        for metadata in self.file_index.values():
            ext = metadata.get('extension', 'no extension')
            extensions[ext] = extensions.get(ext, 0) + 1

        return {
            'total_files': total_files,
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'extensions': extensions,
            'last_indexed': datetime.now().isoformat()
        }

    def add_file_metadata(self, filepath: str, metadata: Dict[str, Any]):
        """Add custom metadata to a file"""
        if filepath in self.file_index:
            if 'custom_metadata' not in self.file_index[filepath]:
                self.file_index[filepath]['custom_metadata'] = {}
            self.file_index[filepath]['custom_metadata'].update(metadata)
            self._save_index()

    def get_file_metadata(self, filepath: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific file"""
        return self.file_index.get(filepath)

    def export_index(self, export_path: str) -> bool:
        """Export index to JSON file"""
        try:
            export_data = {
                'base_directory': str(self.base_directory),
                'export_time': datetime.now().isoformat(),
                'stats': self.get_file_stats(),
                'file_index': self.file_index
            }

            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            print(f"Index exported to {export_path}")
            return True
        except Exception as e:
            print(f"Error exporting index: {e}")
            return False


# Usage Example
async def main():
    # Make sure the directory exists
    target_dir = "../my_files"
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
        print(f"Created directory: {target_dir}")

    # Create a test file first
    test_file_path = os.path.join(target_dir, "example.txt")
    if not os.path.exists(test_file_path):
        with open(test_file_path, 'w') as f:
            f.write("This is a test file for MCP!")
        print(f"Created test file: {test_file_path}")

    async with MCPFilesystemManager(target_dir) as fm:
        # Read a file
        content = await fm.read_file("example.txt")
        print(f"File content: {content}")

        # Write a file
        success = await fm.write_file("test.txt", "Hello from MCP!")
        print(f"Write file success: {success}")

        # List directory
        files = await fm.list_directory(".")
        print(f"Directory contents: {files}")

        # Search files
        txt_files = fm.search_files(".txt", "extension")
        print(f"Text files: {len(txt_files)}")

        # Get file stats
        stats = fm.get_file_stats()
        print(f"File statistics: {stats}")

        # Add custom metadata
        fm.add_file_metadata("test.txt", {
            "author": "User",
            "category": "test",
            "tags": ["mcp", "filesystem"]
        })

        # Export index
        fm.export_index("file_index_export.json")


if __name__ == "__main__":
    # Set event loop policy for Windows to avoid transport warnings
    if os.name == 'nt':  # Windows
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    asyncio.run(main())