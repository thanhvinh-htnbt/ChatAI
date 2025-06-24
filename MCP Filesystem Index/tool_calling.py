import ollama
import asyncio
import MCPFilesystemManager

tools = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Đọc nội dung của một file văn bản trong thư mục được quản lý.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Đường dẫn tương đối đến file cần đọc"
                    }
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Ghi nội dung vào một file văn bản.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Đường dẫn file"
                    },
                    "content": {
                        "type": "string",
                        "description": "Nội dung cần ghi"
                    }
                },
                "required": ["filepath", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "refresh_filesystem_index",
            "description": "Làm mới lại chỉ mục (index) của hệ thống file, quét lại các file trong thư mục đã quản lý để cập nhật trạng thái.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Lấy danh sách các file trong thư mục đã quản lý.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Tìm kiếm các file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Giá trị truy vấn"
                    },
                    "search_type": {
                        "type": "string",
                        "description": "Loại tìm kiếm như name, extension, path, size"
                    }
                },
                "required": ["query", "search_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_stats",
            "description": "Lấy thống kê các file trong thư mục đã quản lý.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_file_metadata",
            "description": "Thêm metadata cho file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Đường dẫn file"
                    },
                    "metadata": {
                        "type": "string",
                        "description": "Metadata cần thêm cho file"
                    }
                },
                "required": ["filepath", "metadata"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_metadata",
            "description": "Lấy metadata của file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Đường dẫn file"
                    }
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "export_index",
            "description": "Xuất chỉ mục (index) của hệ thống file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "export_path": {
                        "type": "string",
                        "description": "Đường dẫn vị trí cần xuất file index"
                    }
                },
                "required": ["export_path"]
            }
        }
    }
]


async def handle_function_call(function_name: str, arguments: dict) -> str:
    async with MCPFilesystemManager.MCPFilesystemManager("../my_files") as fm:
        if function_name == "read_file":
            content = await fm.read_file(arguments["filepath"])
            return content or "[Không đọc được nội dung file]"

        elif function_name == "write_file":
            success = await fm.write_file(arguments["filepath"], arguments["content"])
            return "Ghi thành công" if success else "Ghi thất bại"

        elif function_name == "refresh_filesystem_index":
            await fm.refresh_index()
            return "Đã làm mới chỉ mục hệ thống file thành công."

        elif function_name == "list_directory":
            files = await fm.list_directory()
            return f"Nội dung chứa trong thư mục: {files}"

        elif function_name == "search_files":
            files = await fm.search_files(arguments["query"], arguments["search_type"])
            return f"Các file tìm thấy: {files}"

        elif function_name == "get_file_metadata":
            metadata = await fm.get_file_metadata(arguments["filepath"])
            return f"Metadata của file: {metadata}"

        elif function_name == "add_file_metadata":
            success = await fm.add_file_metadata(arguments["filepath"], arguments["metadata"])
            return "Thêm metadata cho file thành công" if success else "Thêm metadata cho file thất bại"

        elif function_name == "export_index":
            success = await fm.export_index(arguments["export_path"])
            return "Xuất file chỉ mục (index) thành công" if success else "Xuất file chỉ mục (index) thất bại"
        else:
            return f"[Chưa hỗ trợ function: {function_name}]"


async def tool_calling(user_prompt):
    response = ollama.chat(
        model="llama3.2",
        messages=[{"role": "user", "content": user_prompt}],
        tools=tools
    )

    message = response['message']

    if 'tool_calls' in message and message['tool_calls']:
        tool_call = message['tool_calls'][0]
        function_name = tool_call['function']['name']
        arguments = tool_call['function']['arguments']

        result = await handle_function_call(function_name, arguments)
        return result

    return message.get("content", "[Không có nội dung phản hồi]")




if __name__ == "__main__":
    response = asyncio.run(tool_calling("Đọc file test.txt"))
    print(response)
    response = asyncio.run(tool_calling("Viết file test.txt với nội dung: New technologies in Software development \n ChatAI \n Tool Calling"))
    print(response)
    response = asyncio.run(tool_calling("Làm mới chỉ mục"))
    print(response)
    response = asyncio.run(tool_calling("Lấy danh sách các file trong thư mục"))
    print(response)
    response = asyncio.run(tool_calling("Tìm file example.txt"))
    print(response)
    response = asyncio.run(tool_calling("Lấy metadata của example.txt"))
    print(response)
    response = asyncio.run(tool_calling("Thêm metadata cho example.txt với metadata sau: {'category': 'test', 'tags': ['mcp', 'filesystem']}"))
    print(response)
    response = asyncio.run(tool_calling("Xuất file chỉ mục ra ../my_files/index.json"))
    print(response)


