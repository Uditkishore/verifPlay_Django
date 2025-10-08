import tempfile
import os
from django.http import FileResponse
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from .serializer import CircuitFileUploadSerializer
from .circuit_generator import DynamicCircuitDiagram


class GenerateCircuitDiagramView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = CircuitFileUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'error': 'Invalid file',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = serializer.validated_data['file']

        try:
            # Save uploaded Excel temporarily
            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp_file:
                for chunk in uploaded_file.chunks():
                    tmp_file.write(chunk)
                tmp_file.flush()
                excel_path = tmp_file.name

            # Generate figure
            generator = DynamicCircuitDiagram()
            fig = generator.generate_diagram(excel_path)

            os.unlink(excel_path)  # cleanup Excel immediately (safe)

            if fig is None:
                return Response({
                    'error': 'Failed to generate diagram',
                    'message': 'Please check your Excel file format'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Save figure as PNG (don’t auto-delete yet)
            tmp_img = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            fig.write_image(tmp_img.name, format="png", width=1000, height=800)
            tmp_img.close()  # release lock on Windows

            # Open file again for response
            response = FileResponse(open(tmp_img.name, "rb"), content_type="image/png")
            response["Content-Disposition"] = 'attachment; filename="circuit_diagram.png"'

            # Instead of deleting immediately, schedule deletion after response
            def cleanup(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass

            import threading
            threading.Timer(5.0, cleanup, args=[tmp_img.name]).start()

            return response

        except Exception as e:
            return Response({
                'error': 'Processing failed',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



import pandas as pd
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from bokeh.plotting import figure
from bokeh.embed import file_html
from bokeh.resources import CDN
from bokeh.models import Arrow, NormalHead

class CircuitDiagramAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        excel_file = request.FILES.get("file")
        if not excel_file:
            return HttpResponse("Please upload an Excel file.", status=400)

        # Read Excel into DataFrame
        df = pd.read_excel(excel_file)

        # Separate Masters and Slaves
        masters = df[df["Device_Type"] == "Master"]["From_Device"].unique().tolist()
        slaves = df[df["Device_Type"] == "Slave"]["From_Device"].unique().tolist()

        # Create Bokeh figure
        p = figure(title="Circuit Diagram", 
                   x_range=(0, 1000), 
                   y_range=(0, 800),
                   width=1000, height=800)

        device_positions = {}

        # Place Masters on the left
        for i, m in enumerate(masters):
            x, y = 200, 700 - i * 200
            device_positions[m] = (x, y)
            p.rect(x, y, width=80, height=50, fill_color="lightblue")
            p.text(x, y, text=[m], text_align="center", text_baseline="middle")

        # Place Slaves on the right
        for j, s in enumerate(slaves):
            x, y = 800, 700 - j * 200
            device_positions[s] = (x, y)
            p.rect(x, y, width=80, height=50, fill_color="lightgreen")
            p.text(x, y, text=[s], text_align="center", text_baseline="middle")

        # Draw connections (buses with arrows)
        for _, row in df.iterrows():
            from_dev, to_dev = row["From_Device"], row["To_Device"]
            bus_label = row.get("Bus_Label", "")

            if from_dev in device_positions and to_dev in device_positions:
                x0, y0 = device_positions[from_dev]
                x1, y1 = device_positions[to_dev]

                # Add arrow from master to slave
                arrow = Arrow(end=NormalHead(size=10, fill_color="black"),
                              x_start=x0 + 40, y_start=y0,
                              x_end=x1 - 40, y_end=y1,
                              line_width=2)
                p.add_layout(arrow)

                # Add bus label in middle
                if bus_label:
                    mid_x, mid_y = (x0 + x1) / 2, (y0 + y1) / 2
                    p.text(mid_x, mid_y, text=[bus_label], text_align="center")

        # Export as HTML
        html = file_html(p, CDN, "Circuit Diagram")
        return HttpResponse(html)


import pandas as pd
import networkx as nx
from bokeh.plotting import figure
from bokeh.models import Arrow, NormalHead
from bokeh.embed import file_html
from bokeh.resources import CDN
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import HttpResponse


class CircuitAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        excel_file = request.FILES.get("file")
        if not excel_file:
            return HttpResponse("Please upload an Excel file.", status=400)

        # Load Excel (now without Parent column)
        df = pd.read_excel(excel_file)

        # Define layer order
        layer_map = {
            "Manager": 0,
            "Initiator": 1,
            "Switch": 2,
            "Target": 3,
            "Subordinate": 4,
        }

        # Build graph
        G = nx.DiGraph()

        # Step 1: Add all nodes (no parent anymore)
        for _, row in df.iterrows():
            node = row["Node"]
            G.add_node(node, type=row["Type"])

        # Step 2: Add edges
        for _, row in df.iterrows():
            if pd.notna(row["Connects_To"]):
                target = row["Connects_To"]
                if target not in G.nodes:
                    G.add_node(target, type="Unknown")
                G.add_edge(row["Node"], target)

        # Assign layers
        for node in G.nodes:
            node_type = G.nodes[node].get("type", "Unknown")
            layer = layer_map.get(node_type, len(layer_map))
            G.nodes[node]["layer"] = layer

        # Initial multipartite layout
        pos = nx.multipartite_layout(G, subset_key="layer", align="horizontal")

        # Enforce horizontal ordering + spacing
        def reorder_nodes(node_type, spacing=3.0, vertical_gap=3.0):
            nodes = [n for n in G.nodes if node_type in G.nodes[n].get("type", "")]
            nodes_sorted = sorted(nodes, key=lambda x: int("".join(filter(str.isdigit, x)) or 0))
            if nodes_sorted:
                layer = layer_map.get(node_type, 0)
                y_level = layer * vertical_gap
                for i, node in enumerate(nodes_sorted):
                    pos[node] = (i * spacing, y_level)

        reorder_nodes("Manager")
        reorder_nodes("Initiator")
        reorder_nodes("Switch")
        reorder_nodes("Target")
        reorder_nodes("Subordinate")

        # --- Box size for all nodes ---
        box_width = 1.8
        box_height = 0.9

        # --- Compute dynamic bounds ---
        xs, ys = zip(*pos.values())
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)

        margin_x = box_width * 2
        margin_y = box_height * 2

        x_range = (x_min - margin_x, x_max + margin_x)
        y_range = (y_min - margin_y, y_max + margin_y)

        # --- Fixed plot size, but dynamic ranges ---
        p = figure(
            title="Circuit Diagram",
            x_range=x_range,
            y_range=y_range,
            width=1200,   # fixed frame width
            height=700,   # fixed frame height
            match_aspect=True,
            tools=""  # no pan/zoom/reset
        )

        # Clean background (white, no axes/grid)
        p.xaxis.visible = False
        p.yaxis.visible = False
        p.xgrid.visible = False
        p.ygrid.visible = False
        p.outline_line_color = None

        # Color mapping
        color_map = {
            "Manager": "lightblue",
            "Initiator": "orange",
            "Switch": "lightgreen",
            "Target": "pink",
            "Subordinate": "violet",
        }

        # Draw nodes
        for node, (x, y) in pos.items():
            node_type = G.nodes[node].get("type", "Unknown")
            color = color_map.get(node_type, "gray")
            p.rect(x, y, width=box_width, height=box_height,
                   fill_color=color, line_color="black", line_width=2)
            p.text(x, y, text=[node],
                   text_align="center", text_baseline="middle", text_font_size="14pt")

        # Draw arrows (edge clipping at box borders)
        for src, dst in G.edges():
            x0, y0 = pos[src]
            x1, y1 = pos[dst]

            dx = x1 - x0
            dy = y1 - y0
            dist = (dx**2 + dy**2) ** 0.5
            if dist == 0:
                continue

            ux, uy = dx / dist, dy / dist

            x0_adj = x0 + ux * (box_width / 2 if abs(dx) > abs(dy) else box_height / 2)
            y0_adj = y0 + uy * (box_height / 2 if abs(dy) >= abs(dx) else box_width / 2)

            x1_adj = x1 - ux * (box_width / 2 if abs(dx) > abs(dy) else box_height / 2)
            y1_adj = y1 - uy * (box_height / 2 if abs(dy) >= abs(dx) else box_width / 2)

            p.add_layout(Arrow(end=NormalHead(size=12),
                               x_start=x0_adj, y_start=y0_adj,
                               x_end=x1_adj, y_end=y1_adj,
                               line_width=2))

        # Export
        html = file_html(p, CDN, "Circuit Diagram")
        return HttpResponse(html)

import os
import shutil
import tempfile
import subprocess
import pandas as pd
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
import re

MERMAID_THEME = "default"

class MermaidCircuitAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get("file")
        out_format = request.data.get("format", "png").lower()

        if not file_obj:
            return Response({"error": "No file uploaded"}, status=status.HTTP_400_BAD_REQUEST)

        if out_format not in ["png", "jpg"]:
            return Response({"error": "Invalid format, choose 'png' or 'jpg'"},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            df = pd.read_excel(file_obj)

            required_columns = {"Node", "Connects_To"}
            if not required_columns.issubset(df.columns):
                return Response({
                    "error": f"Excel must contain at least these columns: {required_columns}"
                }, status=status.HTTP_400_BAD_REQUEST)

            mmd_text = self._generate_mermaid(df)

            image_data, content_type = self._render_mermaid(mmd_text, out_format)
            return HttpResponse(image_data, content_type=content_type)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _slug(self, label: str) -> str:
        """Make safe IDs for Mermaid nodes."""
        s = re.sub(r"\W+", "_", str(label).strip())
        if not re.match(r"^[A-Za-z]", s):
            s = "N_" + s
        return s

    def _detect_type(self, label: str) -> str:
        """Detect node category from label."""
        l = label.lower()
        if "switch" in l:
            return "switch"
        if "initiator" in l:
            return "initiator"
        if "target" in l:
            return "target"
        if "manager" in l:
            return "manager"
        if "subordinate" in l:
            return "subordinate"
        return "other"

    def _generate_mermaid(self, df: pd.DataFrame) -> str:
        lines = ["flowchart TB"]

        nodes = set()
        edges = []

        for _, row in df.iterrows():
            a = str(row["Node"]).strip()
            b = str(row["Connects_To"]).strip() if pd.notna(row["Connects_To"]) else ""

            if a: nodes.add(a)
            if b: nodes.add(b)
            if a and b:
                edges.append((a, b))

        # Add nodes with proper escaping
        for n in nodes:
            nid = self._slug(n)
            ntype = self._detect_type(n)
            # Escape quotes and special characters in labels
            safe_label = n.replace('"', '&quot;').replace("'", "&#39;")
            lines.append(f'{nid}["{safe_label}"]:::cls_{ntype}')

        # Add edges
        for a, b in edges:
            lines.append(f"{self._slug(a)} --> {self._slug(b)}")

        # Add an empty line before styling for better readability
        lines.append("")

        # Styling with proper syntax (no quotes around color values)
        lines += [
            "classDef cls_switch fill:#3399ff,stroke:#000,color:#ffffff",
            "classDef cls_initiator fill:#ffcccc,stroke:#000,color:#000000",
            "classDef cls_target fill:#ff9966,stroke:#000,color:#000000",
            "classDef cls_manager fill:#ffff99,stroke:#000,color:#000000",
            "classDef cls_subordinate fill:#cc99ff,stroke:#000,color:#000000",
            "classDef cls_other fill:#dddddd,stroke:#000,color:#000000",
        ]
        
        return "\n".join(line.strip() for line in lines if line.strip())

    def _render_mermaid(self, mmd_text: str, out_format: str):
        with tempfile.TemporaryDirectory() as td:
            in_path = os.path.join(td, "diagram.mmd")
            out_ext = "png" if out_format == "png" else "jpg"
            out_path = os.path.join(td, f"diagram.{out_ext}")

            with open(in_path, "w", encoding="utf-8") as f:
                f.write(mmd_text)

            mmdc_path = shutil.which("mmdc") or shutil.which("mmdc.cmd")
            if not mmdc_path:
                raise FileNotFoundError("Mermaid CLI (mmdc) not found. Install globally: npm install -g @mermaid-js/mermaid-cli")

            # Run and capture error
            result = subprocess.run(
                [mmdc_path, "-i", in_path, "-o", out_path, "-t", MERMAID_THEME, "-b", "transparent"],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                debug_path = os.path.join(td, "debug_diagram.mmd")
                with open(debug_path, "w", encoding="utf-8") as dbg:
                    dbg.write(mmd_text)

                raise RuntimeError(
                    f"Mermaid render failed with code {result.returncode}\n"
                    f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}\n\n"
                    f"Mermaid input was saved at: {debug_path}\n"
                    f"Generated Mermaid code:\n"
                    f"---\n"
                    f"{mmd_text}\n"
                    f"---"
                )

            with open(out_path, "rb") as f:
                blob = f.read()

            content_type = "image/png" if out_ext == "png" else "image/jpeg"
            return blob, content_type