import pandas as pd
import re
import os
import base64
import faiss
import torch
import pymongo
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer



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

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
client = pymongo.MongoClient(MONGO_URI)
db = client["Verif_Playground"]
collection = db.get_collection("scripts")

# Embedding model
model = SentenceTransformer("all-MiniLM-L6-v2")

# Helper functions
def extract_text_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator="\n").strip()

def is_base64(text):
    clean = re.sub(r"<[^>]+>", "", text).strip().replace("\n", "").replace(" ", "")
    if len(clean) < 100:
        return False
    try:
        base64.b64decode(clean, validate=True)
        return True
    except:
        return False

def decode_base64(text):
    try:
        padded = text + "=" * (-len(text) % 4)
        return base64.b64decode(padded).decode("utf-8", errors="ignore")
    except:
        return None

# Build index
def build_faiss_index():
    docs = []
    metadatas = []

    for doc in collection.find():
        html_data = doc.get("htmlData", "")
        if not html_data:
            continue

        # Try decoding base64, else treat as plain HTML
        if is_base64(html_data):
            decoded = decode_base64(html_data)
            if not decoded:
                continue
            text = extract_text_from_html(decoded)
        else:
            text = extract_text_from_html(html_data)

        if not text.strip():
            continue

        docs.append(text)
        metadatas.append({
            "_id": str(doc["_id"]),
            "fileName": doc.get("fileName", "unknown")
        })

    # Generate embeddings
    if not docs:
        raise ValueError("No valid documents found to index.")
    
    embeddings = model.encode(docs, convert_to_tensor=True)
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings.cpu().numpy())

    return index, docs, metadatas



# Answer question
def query_documents(question, index, docs, metadatas, top_k=3):
    q_embedding = model.encode([question])
    D, I = index.search(q_embedding, top_k)
    results = [docs[i] for i in I[0]]
    scores = D[0]

    # Check distance thresholds (smaller is better in L2)
    best_score = scores[0]
    best_result = results[0]

    # Tune threshold as needed (e.g. 1.5 for MiniLM)
    if best_score < 1.5:
        return best_result
    else:
        for res in results:
            if re.search(re.escape(question), res, re.IGNORECASE):
                return res
        return "Sorry, I'm not trained for this specific topic."

