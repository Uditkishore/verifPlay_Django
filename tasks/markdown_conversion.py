import os
from markitdown import MarkItDown

def convert_to_markdown(input_path, output_path):
    """
    Convert the given file to Markdown format and save it to output_path.
    Supports various file types like PDF, DOCX, JSON, XML, XLSX, TXT, etc.
    """
    try:
        # Convert the file using markitdown
        markdown_content = MarkItDown(input_path)

        # Ensure the output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Write the markdown to the output file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

        print(f"Converted '{input_path}' to Markdown at '{output_path}'")
    except Exception as e:
        print(f"Failed to convert '{input_path}': {e}")


