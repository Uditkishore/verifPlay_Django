import pandas as pd
import re
import os
import base64
import faiss
import torch
import pymongo
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer
import subprocess
import tempfile
from io import StringIO
from django.conf import settings
import faiss
import fitz 


def parse_field(field_str):
    """
    Parse a field definition string like 'BUFFER_SIZE [15:0]' to extract:
    - Field name
    - LSB position
    - MSB position
    - Field size
    """
    if isinstance(field_str, str):
        # Match field name and index range, e.g., 'BUFFER_SIZE [15:0]'
        match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)(?:\s*\[(\d+):(\d+)\])?", field_str)
        if match:
            field_name = match.group(1).strip()
            msb = int(match.group(2)) if match.group(2) else 0  # Handle case where range is not provided
            lsb = int(match.group(3)) if match.group(3) else 0
            size = msb - lsb + 1 if msb and lsb else 1  # Default to size 1 if no range
            return field_name, size, lsb, msb
    return None, None, None, None

def excel_to_uvm_ral(excel_file, output_file):
    try:
        # Read the Excel file
        df = pd.read_excel(excel_file, header=None)

        # Strip all column names of leading/trailing whitespace
        df.columns = df.iloc[0].str.strip()
        df = df[1:]

        # Check if the necessary columns are present
        required_columns = ['Register Name', 'Offset', 'Read/Write', 'Fields', 'Default value', 'Reset value', 'Description']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            print(f"Error: Missing required columns: {', '.join(missing_columns)}")
            return

        # Map column names to expected names
        column_map = {
            'Register Name': 'register_name',
            'Offset': 'offset',
            'Read/Write': 'read_write',
            'Fields': 'fields',
            'Default value': 'default_value',
            'Reset value': 'reset_value',
            'Description': 'description'
        }
        df.rename(columns=column_map, inplace=True)

        # Convert all relevant columns to strings and fill NaN with default values
        df['register_name'] = df['register_name'].fillna("").astype(str)
        df['fields'] = df['fields'].fillna("").astype(str)

        # Open the output file for writing
        with open(output_file, 'w') as f:
            # Write the UVM RAL header
            f.write("`ifndef REG_MODEL\n")
            f.write("`define REG_MODEL\n\n")

            current_reg = None
            fields = []

            for _, row in df.iterrows():
                reg_name = row['register_name'].strip()
                reg_offset = row['offset']
                read_write = row['read_write']
                fields_str = row['fields']
                default_value = row['default_value']
                reset_value = row['reset_value']
                description = row['description']

                # If we encounter a new register, write out the previous register and its fields
                if reg_name:  # Register name found
                    # If we're already processing a register, close it out
                    if current_reg:
                        # Write the previous register's field instances (before constructor)
                        f.write(f"  //---------------------------------------\n")
                        for field in fields:
                            field_name, size, lsb, msb = parse_field(field.strip())
                            if field_name and size and lsb is not None:
                                f.write(f"    rand uvm_reg_field {field_name};\n")
                        
                        # Write the build_phase only once
                        f.write(f"  //---------------------------------------\n")
                        f.write("  function void build;\n")
                        for field in fields:  # Indentation fixed here
                            field_name, size, lsb, msb = parse_field(field.strip())
                            if field_name and size and lsb is not None:
                               f.write(f"    {field_name} = uvm_reg_field::type_id::create(\"{field_name}\");\n")
                               f.write(f"    {field_name}.configure(.parent(this),\n")
                               f.write(f"                           .size({size}),\n")
                               f.write(f"                           .lsb_pos({lsb}),\n")
                               f.write(f"                           .msb_pos({msb}),\n")
                               f.write(f"                           .access(\"{read_write}\"),\n")
                               f.write(f"                           .volatile(0),\n")
                               f.write(f"                           .reset({default_value if pd.notna(default_value) else 0}),\n")
                               f.write(f"                           .has_reset(1),\n")
                               f.write(f"                           .is_rand(1),\n")
                               f.write(f"                           .individually_accessible(0));\n")
                        f.write("  endfunction\n")
                        f.write("endclass\n\n")

                    # Now process the new register
                    f.write(f"class {reg_name} extends uvm_reg;\n")
                    f.write(f"  `uvm_object_utils({reg_name})\n\n")
                    f.write("  //---------------------------------------\n")

                    # Initialize new fields list
                    fields = []
                    current_reg = reg_name

                    # Write register constructor (only once)
                    f.write(f"  // Constructor\n")
                    f.write(f"  //---------------------------------------\n")
                    f.write(f"  function new(string name = \"{reg_name}\");\n")
                    f.write(f"    super.new(name, 32, UVM_NO_COVERAGE);\n")
                    f.write(f"  endfunction\n\n")
                # Add fields to the list
                if fields_str:  # Process each field for the current register
                    fields.append(fields_str.strip())

            # After the last register, write it out
            if current_reg:
                # Write the last register's field instances and configuration
                f.write(f"  //---------------------------------------\n")
                for field in fields:
                    field_name, size, lsb, msb = parse_field(field.strip())
                    if field_name and size and lsb is not None:
                        f.write(f"    rand uvm_reg_field {field_name};\n")
                        f.write(f"    {field_name} = uvm_reg_field::type_id::create(\"{field_name}\");\n")
                        f.write(f"    {field_name}.configure(.parent(this),\n")
                        f.write(f"                           .size({size}),\n")
                        f.write(f"                           .lsb_pos({lsb}),\n")
                        f.write(f"                           .msb_pos({msb}),\n")
                        f.write(f"                           .access(\"{read_write}\"),\n")
                        f.write(f"                           .volatile(0),\n")
                        f.write(f"                           .reset({default_value if pd.notna(default_value) else 0}),\n")
                        f.write(f"                           .has_reset(1),\n")
                        f.write(f"                           .is_rand(1),\n")
                        f.write(f"                           .individually_accessible(0));\n")
                f.write("  endfunction\n")
                f.write("endclass\n\n")

            # Generate the register block class
            f.write("//-------------------------------------------------------------------------\n")
            f.write("//\tRegister Block Definition\n")
            f.write("//-------------------------------------------------------------------------\n")
            f.write("class dma_reg_model extends uvm_reg_block;\n")
            f.write("  `uvm_object_utils(dma_reg_model)\n\n")
            f.write("  //---------------------------------------\n")
            f.write("  // Register Instances\n")
            f.write("  //---------------------------------------\n")

            for reg_name in df['register_name'].dropna().unique():
                f.write(f"  rand {reg_name} reg_{reg_name.lower()};\n")

            f.write("\n  //---------------------------------------\n")
            f.write("  // Constructor\n")
            f.write("  //---------------------------------------\n")
            f.write("  function new (string name = \"\");\n")
            f.write("    super.new(name, build_coverage(UVM_NO_COVERAGE));\n")
            f.write("  endfunction\n\n")
            f.write("  //---------------------------------------\n")
            f.write("  // Build Phase\n")
            f.write("  //---------------------------------------\n")
            f.write("  function void build();\n")

            for reg_name in df['register_name'].dropna().unique():
                f.write(f"    reg_{reg_name.lower()} = {reg_name}::type_id::create(\"reg_{reg_name.lower()}\");\n")
                f.write(f"    reg_{reg_name.lower()}.build();\n")
                f.write(f"    reg_{reg_name.lower()}.configure(this);\n")

            f.write("    //---------------------------------------\n")
            f.write("    // Memory Map Creation and Register Map\n")
            f.write("    //---------------------------------------\n")
            f.write("    default_map = create_map(\"my_map\", 0, 4, UVM_LITTLE_ENDIAN);\n")
            for reg_name in df['register_name'].dropna().unique():
                f.write(f"    default_map.add_reg(reg_{reg_name.lower()}, 'h0, \"RW\");\n")

            f.write("    lock_model();\n")
            f.write("  endfunction\n")
            f.write("endclass\n\n")

            f.write("`endif // REG_MODEL\n")

        print(f"UVM RAL file generated: {output_file}")

    except Exception as e:
        print(f"Error: {e}")


# MongoDB setup
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
client = pymongo.MongoClient(MONGO_URI)
db = client["Verif_Playground"]
collection = db.get_collection("scripts")

# Embedding model
model = SentenceTransformer("all-MiniLM-L6-v2")

# Extract plain text from HTML
def extract_text_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator="\n").strip()

# Extract plain text from PDF bytes
def extract_text_from_pdf_bytes(pdf_bytes):
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            return "\n".join(page.get_text() for page in doc)
    except Exception:
        return ""

# Detect if a string is base64
def is_base64(text):
    clean = re.sub(r"<[^>]+>", "", text).strip().replace("\n", "").replace(" ", "")
    if len(clean) < 100:
        return False
    try:
        base64.b64decode(clean, validate=True)
        return True
    except Exception:
        return False

# Decode base64 safely
def decode_base64(text):
    try:
        padded = text + "=" * (-len(text) % 4)
        return base64.b64decode(padded)
    except Exception:
        return None

# Split long text into chunks
def chunk_text(text, chunk_size=500, overlap=100):
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk:
            chunks.append(chunk.strip())
    return chunks

# Build FAISS index
def build_faiss_index():
    docs = []
    metadatas = []

    for doc in collection.find():
        file_type = doc.get("fileType", "").lower()
        html_data = doc.get("htmlData", "")
        base64_data = doc.get("base64", "")

        text = ""
        if file_type == "html":
            if is_base64(html_data):
                decoded = decode_base64(html_data)
                if decoded:
                    text = extract_text_from_html(decoded.decode("utf-8", errors="ignore"))
            else:
                text = extract_text_from_html(html_data)

        elif file_type == "pdf":
            if is_base64(base64_data):
                decoded = decode_base64(base64_data)
                if decoded:
                    text = extract_text_from_pdf_bytes(decoded)
                    if not text.strip():
                        # text = extract_text_from_html(decoded.decode("utf-8", errors="ignore"))
                        continue

        if not text.strip():
            continue

        for chunk in chunk_text(text):
            docs.append(chunk)
            metadatas.append({
                "_id": str(doc.get("_id")),
                "fileName": doc.get("fileName", "unknown")
            })

    if not docs:
        raise ValueError("No valid documents found to index.")

    embeddings = model.encode(docs, convert_to_tensor=True)
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings.cpu().numpy())

    return index, docs, metadatas

# Search documents
def query_documents(question, index, docs, metadatas, top_k=3):
    if index is None:
        return "Error: FAISS index not initialized."

    q_embedding = model.encode([question])
    D, I = index.search(q_embedding, top_k)
    results = [docs[i] for i in I[0]]
    scores = D[0]

    best_score = scores[0]
    best_result = results[0]

    if best_score < 1.6:
        return best_result

    question_keywords = re.findall(r"\w+", question.lower())
    for doc in docs:
        doc_lower = doc.lower()
        if any(word in doc_lower for word in question_keywords):
            return doc

    return "Sorry, I'm not trained for this specific topic."

# On module import, build index
try:
    faiss_index, faiss_docs, faiss_meta = build_faiss_index()
except Exception:
    faiss_index = None
    faiss_docs = []
    faiss_meta = []

def run_mux_simulation(design_file, tb_file):
    with tempfile.TemporaryDirectory() as temp_dir:
        design_path = os.path.join(temp_dir, "mux_design.sv")
        tb_path = os.path.join(temp_dir, "mux_tb.py")
        makefile_path = os.path.join(temp_dir, "Makefile")
        excel_output_path = os.path.join(temp_dir, "mux_result.xlsx")
        vcd_output_path = os.path.join(temp_dir, "dump.vcd")

        # Output files to be saved inside settings.MEDIA_ROOT
        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
        excel_copy_path = os.path.join(settings.MEDIA_ROOT, "mux_simulation_result.xlsx")
        vcd_copy_path = os.path.join(settings.MEDIA_ROOT, "mux_dump.vcd")

        # Save uploaded files
        with open(design_path, 'wb') as f:
            f.write(design_file.read())
        with open(tb_path, 'wb') as f:
            f.write(tb_file.read())

        # Create Makefile with just filenames (not full paths)
        makefile_content = f"""
TOPLEVEL_LANG ?= verilog
SIM ?= icarus
VERILOG_SOURCES = mux_design.sv
TOPLEVEL := mux
MODULE := mux_tb

include $(shell cocotb-config --makefiles)/Makefile.sim
"""
        with open(makefile_path, 'w') as f:
            f.write(makefile_content)

        # Convert Windows path to WSL format: C:\Users\hi\... -> /mnt/c/Users/hi/...
        wsl_path = temp_dir.replace("\\", "/").replace(":", "")
        wsl_path = "/mnt/" + wsl_path[0].lower() + wsl_path[1:]

        # Correct subprocess call: export PATH and run inside bash correctly
        result = subprocess.run(
            ["wsl", "bash", "-c", f"export PATH=\"$HOME/.local/bin:$PATH\" && cd '{wsl_path}' && make sim=icarus"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode != 0:
            return {"error": "Simulation failed", "output": result.stderr}

        output = result.stdout

        # Parse lines like: a: 44 b: 177 c: 95 d: 253 sel: 3 dout: 253
        pattern = re.compile(r"a: (\d+) b: (\d+) c: (\d+) d: (\d+) sel: (\d+) dout: (\d+)")
        rows = pattern.findall(output)

        if not rows:
            return {"error": "No waveform-style data found in simulation output", "output": output}

        df = pd.DataFrame(rows, columns=["a", "b", "c", "d", "sel", "dout"])
        df.to_excel(excel_output_path, index=False)

        # Save Excel to media folder
        with open(excel_output_path, 'rb') as fsrc, open(excel_copy_path, 'wb') as fdst:
            fdst.write(fsrc.read())

        # Copy VCD to media folder
        if os.path.exists(vcd_output_path):
            with open(vcd_output_path, 'rb') as fsrc, open(vcd_copy_path, 'wb') as fdst:
                fdst.write(fsrc.read())

        return {
            "message": "Simulation successful",
            "excel_file": settings.MEDIA_URL + "mux_simulation_result.xlsx",
            "vcd_file": settings.MEDIA_URL + "mux_dump.vcd",
            "stdout": output,
            "df": df
        }
