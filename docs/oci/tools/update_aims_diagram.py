#!/usr/bin/env python3
"""Append reproducible AIMS-specific operational pages to the Draw.io workbook."""

from __future__ import annotations

import copy
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


PAGE_WIDTH = 1800
PAGE_HEIGHT = 1200


COLORS = {
    "ink": "#312D2A",
    "muted": "#5F5F5F",
    "shared": "#FFF2CC",
    "shared_stroke": "#D6B656",
    "oe": "#D9EAF7",
    "oe_stroke": "#4A86A8",
    "env": "#E2F0D9",
    "env_stroke": "#70AD47",
    "security": "#FCE4D6",
    "security_stroke": "#C55A11",
    "network": "#EAF3F8",
    "network_stroke": "#10739E",
    "data": "#E4DFEC",
    "data_stroke": "#8064A2",
    "danger": "#F8CECC",
    "danger_stroke": "#B85450",
    "white": "#FFFFFF",
}


class Page:
    def __init__(self, name: str, page_id: str, title: str, subtitle: str):
        self.diagram = ET.Element("diagram", {"id": page_id, "name": name})
        self.model = ET.SubElement(
            self.diagram,
            "mxGraphModel",
            {
                "dx": "1422",
                "dy": "794",
                "grid": "1",
                "gridSize": "10",
                "guides": "1",
                "tooltips": "1",
                "connect": "1",
                "arrows": "1",
                "fold": "1",
                "page": "1",
                "pageScale": "1",
                "pageWidth": str(PAGE_WIDTH),
                "pageHeight": str(PAGE_HEIGHT),
                "math": "0",
                "shadow": "0",
            },
        )
        self.root = ET.SubElement(self.model, "root")
        ET.SubElement(self.root, "mxCell", {"id": "0"})
        ET.SubElement(self.root, "mxCell", {"id": "1", "parent": "0"})
        self.seq = 0
        self.box(
            title,
            25,
            18,
            1750,
            44,
            fill=COLORS["ink"],
            stroke=COLORS["ink"],
            font="#FFFFFF",
            size=20,
            bold=True,
            align="left",
        )
        self.text(subtitle, 35, 68, 1720, 32, size=11, color=COLORS["muted"], align="left")
        self.box(
            "TARGET-STATE SNAPSHOT • Sơ đồ giữ Network Firewall theo kiến trúc trước khi xóa. "
            "Compute instance có thể đang STOPPED; trạng thái runtime không làm thay đổi thiết kế.",
            35,
            102,
            1720,
            40,
            fill="#FFF4CE",
            stroke="#D6B656",
            font="#7F6000",
            size=11,
            bold=True,
            align="left",
        )

    def _id(self, prefix: str) -> str:
        self.seq += 1
        return f"{prefix}-{self.seq}"

    def vertex(self, value: str, x: float, y: float, w: float, h: float, style: str, *, cell_id: str | None = None):
        cell_id = cell_id or self._id("v")
        cell = ET.SubElement(
            self.root,
            "mxCell",
            {"id": cell_id, "value": value, "style": style, "vertex": "1", "parent": "1"},
        )
        ET.SubElement(
            cell,
            "mxGeometry",
            {"x": str(x), "y": str(y), "width": str(w), "height": str(h), "as": "geometry"},
        )
        return cell_id

    def box(
        self,
        value: str,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        fill: str = "#FFFFFF",
        stroke: str = "#808080",
        font: str = "#000000",
        size: int = 12,
        bold: bool = False,
        rounded: bool = True,
        align: str = "center",
        dashed: bool = False,
        vertical: str = "middle",
        cell_id: str | None = None,
    ) -> str:
        style = (
            f"rounded={1 if rounded else 0};whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
            f"fontColor={font};fontSize={size};fontStyle={1 if bold else 0};align={align};"
            f"verticalAlign={vertical};spacing=8;strokeWidth=1.5;dashed={1 if dashed else 0};"
        )
        return self.vertex(value, x, y, w, h, style, cell_id=cell_id)

    def container(self, title: str, x: float, y: float, w: float, h: float, *, fill: str, stroke: str, cell_id: str | None = None) -> str:
        style = (
            f"swimlane;html=1;whiteSpace=wrap;rounded=0;startSize=36;horizontal=1;fillColor={fill};"
            f"swimlaneFillColor=#FFFFFF;strokeColor={stroke};fontColor={COLORS['ink']};fontSize=14;"
            "fontStyle=1;align=left;spacingLeft=10;strokeWidth=2;collapsible=0;"
        )
        return self.vertex(title, x, y, w, h, style, cell_id=cell_id)

    def text(self, value: str, x: float, y: float, w: float, h: float, *, size: int = 11, color: str = "#000000", bold: bool = False, align: str = "center") -> str:
        style = (
            "text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;verticalAlign=middle;"
            f"align={align};fontSize={size};fontColor={color};fontStyle={1 if bold else 0};"
        )
        return self.vertex(value, x, y, w, h, style)

    def edge(
        self,
        source: str,
        target: str,
        label: str = "",
        *,
        color: str = "#1F4E79",
        width: int = 2,
        dashed: bool = False,
        both: bool = False,
        orthogonal: bool = True,
        label_color: str = "#1F4E79",
    ) -> str:
        style = (
            f"edgeStyle={'orthogonalEdgeStyle' if orthogonal else 'none'};rounded=0;orthogonalLoop=1;"
            f"jettySize=auto;html=1;strokeColor={color};strokeWidth={width};dashed={1 if dashed else 0};"
            f"endArrow=block;endFill=1;startArrow={'block' if both else 'none'};"
            f"startFill={1 if both else 0};fontSize=10;fontColor={label_color};labelBackgroundColor=#FFFFFF;"
        )
        cell_id = self._id("e")
        cell = ET.SubElement(
            self.root,
            "mxCell",
            {
                "id": cell_id,
                "value": label,
                "style": style,
                "edge": "1",
                "parent": "1",
                "source": source,
                "target": target,
            },
        )
        ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
        return cell_id

    def footer(self, text: str):
        self.text(text, 35, 1150, 1720, 28, size=9, color="#666666", align="left")


def routing_page() -> ET.Element:
    p = Page(
        "05 — NET · Routing",
        "aims-routing",
        "AIMS / OCI OPEN LZ — ROUTING WITH HUB B NETWORK FIREWALL",
        "Customized from Oracle pages OPS - OE01 Routing and OPS - Test Network Flows • Region ap-tokyo-1",
    )

    p.container("cmp-network • hub-vcn 10.0.0.0/16", 120, 165, 650, 405, fill=COLORS["shared"], stroke=COLORS["shared_stroke"])
    internet = p.box("Internet", 20, 300, 80, 54, fill="#F2F2F2", stroke="#7F7F7F", bold=True)
    igw = p.box("IGW", 145, 275, 85, 64, fill=COLORS["network"], stroke=COLORS["network_stroke"], bold=True)
    public_lb = p.box("Public LB<br><b>140.245.85.157</b><br>hub-publiclb-sn<br>10.0.2.0/24", 270, 235, 150, 110, fill="#FCE4D6", stroke="#ED7D31", bold=True)
    fw = p.box("OCI Network Firewall<br><b>aims-hub-b-fw</b><br>10.0.3.23<br>hub-fw-sn 10.0.3.0/24", 475, 225, 170, 130, fill=COLORS["danger"], stroke=COLORS["danger_stroke"], bold=True)
    nat = p.box("NAT Gateway<br><b>hub-natgw</b> • Internet egress", 345, 485, 180, 55, fill=COLORS["network"], stroke=COLORS["network_stroke"], bold=True)
    p.box("hub-mgmt-sn 10.0.4.0/24", 155, 405, 175, 54, fill="#FFFFFF", stroke=COLORS["shared_stroke"])
    p.box("hub-monitoring-sn 10.0.5.0/24", 345, 405, 180, 54, fill="#FFFFFF", stroke=COLORS["shared_stroke"])
    p.box("hub-dns-sn 10.0.6.0/24", 155, 485, 175, 54, fill="#FFFFFF", stroke=COLORS["shared_stroke"])

    drg = p.box("DRG<br><b>lz-drg</b><br>Hub-and-spoke transit", 805, 310, 115, 105, fill="#DDEBF7", stroke="#2F75B5", bold=True)

    p.container("cmp-oe01-common-network • oe01-vcn 10.1.0.0/16", 955, 165, 790, 405, fill=COLORS["oe"], stroke=COLORS["oe_stroke"])
    private_lb = p.box("Private LB<br>10.1.2.0/24<br>Traefik → AIMS", 985, 225, 150, 85, fill="#FFFFFF", stroke=COLORS["oe_stroke"], bold=True)
    workers = p.box("OKE workers<br>10.1.1.0/24<br>3 nodes", 1190, 225, 140, 85, fill="#FFFFFF", stroke=COLORS["oe_stroke"], bold=True)
    pods = p.box("VCN-native Pods<br>10.1.16.0/20<br>AIMS • Kafka • DB", 1385, 225, 150, 85, fill=COLORS["env"], stroke=COLORS["env_stroke"], bold=True)
    api = p.box("OKE API<br>10.1.0.0/28<br>:6443 private", 1585, 225, 130, 85, fill="#FFFFFF", stroke=COLORS["oe_stroke"], bold=True)
    bastion = p.box("Bastion endpoint<br>10.1.3.0/28", 1585, 400, 130, 75, fill="#FFFFFF", stroke=COLORS["oe_stroke"])
    sgw = p.box("Service Gateway<br>Oracle Services Network", 1190, 400, 170, 75, fill=COLORS["network"], stroke=COLORS["network_stroke"], bold=True)
    p.box("rt-spoke<br>OSN → SGW<br>0.0.0.0/0 → DRG", 1410, 395, 185, 90, fill="#FFF2CC", stroke="#BF9000", bold=True)

    p.edge(internet, igw, "HTTPS/443", color="#C00000", width=3)
    p.edge(igw, public_lb, "ingress", color="#C00000", width=3)
    p.edge(public_lb, fw, "inspect", color="#C00000", width=3)
    p.edge(fw, drg, "transit", color="#C00000", width=3)
    p.edge(drg, private_lb, "backend HTTP", color="#C00000", width=3)
    p.edge(bastion, api, "admin / 6443", color="#2F5597", dashed=True)
    p.edge(workers, pods, "CNI", color="#548235", both=True)
    p.edge(fw, nat, "egress", color="#BF9000")
    p.edge(workers, sgw, "OSN", color="#4472C4")

    p.container("Routing tables — target state with Network Firewall", 60, 625, 1680, 470, fill="#F7F7F7", stroke="#A6A6A6")
    p.box("<b>OE01 rt-spoke</b><br><br>OSN Services → oe01-sgw<br>0.0.0.0/0 → lz-drg", 90, 690, 275, 150, fill="#FFFFFF", stroke=COLORS["oe_stroke"], align="left")
    p.box("<b>DRG RT: from-spoke</b><br><br>0.0.0.0/0 → att-hub", 390, 690, 250, 150, fill="#FFFFFF", stroke="#2F75B5", align="left")
    p.box("<b>rt-hub-from-drg</b><br><br>0.0.0.0/0 → FW 10.0.3.23<br>10.0.2.0/24 → FW 10.0.3.23", 665, 690, 300, 150, fill="#FFFFFF", stroke=COLORS["danger_stroke"], align="left")
    p.box("<b>rt-hub-fw</b><br><br>10.1.0.0/16 → lz-drg<br>0.0.0.0/0 → hub-natgw", 990, 690, 280, 150, fill="#FFFFFF", stroke=COLORS["danger_stroke"], align="left")
    p.box("<b>rt-hub-publiclb</b><br><br>10.1.0.0/16 → FW 10.0.3.23<br>0.0.0.0/0 → hub-igw", 1295, 690, 300, 150, fill="#FFFFFF", stroke="#ED7D31", align="left")
    p.box("<b>rt-hub-nat-return</b><br><br>10.1.0.0/16 → FW 10.0.3.23<br>10.0.4/24, .5/24, .6/24 → FW", 90, 875, 340, 150, fill="#FFFFFF", stroke="#BF9000", align="left")
    p.box("<b>DRG RT: from-hub</b><br><br>10.1.0.0/16 → att-oe01<br>10.2.0.0/16 → att-oe02 (planned/test)", 460, 875, 330, 150, fill="#FFFFFF", stroke="#2F75B5", align="left")
    p.box("<b>OE02 spoke (planned / Terraform-validated)</b><br><br>VCN 10.2.0.0/16<br>Local OSN → SGW • 0/0 → DRG in firewall target-state<br>Data Science → Kafka OE01 uses inter-OE inspected path", 820, 875, 480, 150, fill=COLORS["data"], stroke=COLORS["data_stroke"], align="left")
    p.box("<b>Symmetric routing rule</b><br><br>Forward and return traffic must cross the same firewall. Do not mix local NAT return with centralized firewall egress.", 1330, 875, 350, 150, fill=COLORS["danger"], stroke=COLORS["danger_stroke"], align="left")
    p.footer("Source layout: Oracle OCI Open LZ Multi-OE Blueprint • AIMS values from live inventory before firewall deletion • Diagram is editable in Draw.io")
    return p.diagram


def test_flows_page() -> ET.Element:
    p = Page(
        "06 — OPS · Test Network Flows",
        "aims-test-network-flows",
        "AIMS / OCI OPEN LZ — TEST NETWORK FLOWS",
        "Expected packet paths and verification points • The numbered paths map to the validation table below",
    )
    internet = p.box("Internet users", 30, 285, 105, 60, fill="#F2F2F2", stroke="#7F7F7F", bold=True)
    hub = p.container("Hub B • hub-vcn 10.0.0.0/16", 180, 175, 570, 360, fill=COLORS["shared"], stroke=COLORS["shared_stroke"])
    lb = p.box("① Public LB<br>140.245.85.157", 220, 245, 130, 75, fill="#FCE4D6", stroke="#ED7D31", bold=True)
    fw = p.box("② Network Firewall<br>10.0.3.23", 400, 235, 150, 95, fill=COLORS["danger"], stroke=COLORS["danger_stroke"], bold=True)
    nat = p.box("⑥ NAT Gateway", 585, 410, 130, 65, fill=COLORS["network"], stroke=COLORS["network_stroke"], bold=True)
    drg = p.box("③ lz-drg", 795, 285, 110, 75, fill="#DDEBF7", stroke="#2F75B5", bold=True)
    oe1 = p.container("OE01 • oe01-vcn 10.1.0.0/16", 950, 175, 800, 360, fill=COLORS["oe"], stroke=COLORS["oe_stroke"])
    plb = p.box("④ Private LB<br>sn-oke-lb", 985, 240, 130, 75, fill="#FFFFFF", stroke=COLORS["oe_stroke"], bold=True)
    ingress = p.box("Traefik ingress", 1150, 240, 125, 75, fill="#FFFFFF", stroke=COLORS["oe_stroke"], bold=True)
    aims = p.box("⑤ AIMS<br>namespace aims", 1310, 225, 135, 100, fill=COLORS["env"], stroke=COLORS["env_stroke"], bold=True)
    kafka = p.box("Kafka TLS/9093<br>namespace kafka", 1480, 225, 135, 100, fill=COLORS["data"], stroke=COLORS["data_stroke"], bold=True)
    pg = p.box("PostgreSQL/5432<br>namespace data", 1645, 225, 85, 100, fill=COLORS["data"], stroke=COLORS["data_stroke"])
    bastion = p.box("OCI Bastion<br>private API", 1040, 405, 130, 70, fill="#FFF2CC", stroke="#BF9000", bold=True)
    api = p.box("OKE API :6443", 1210, 405, 130, 70, fill="#FFFFFF", stroke=COLORS["oe_stroke"])
    sgw = p.box("Service Gateway<br>OSN", 1420, 405, 135, 70, fill=COLORS["network"], stroke=COLORS["network_stroke"])
    object_storage = p.box("Object Storage", 1610, 405, 115, 70, fill=COLORS["network"], stroke=COLORS["network_stroke"])

    p.edge(internet, lb, "1 HTTPS/443", color="#C00000", width=3)
    p.edge(lb, fw, "2 WAF/LB → inspect", color="#C00000", width=3)
    p.edge(fw, drg, "3", color="#C00000", width=3)
    p.edge(drg, plb, "4", color="#C00000", width=3)
    p.edge(plb, ingress, "", color="#C00000", width=3)
    p.edge(ingress, aims, "5", color="#C00000", width=3)
    p.edge(aims, kafka, "events", color="#7030A0", both=True)
    p.edge(aims, pg, "SQL", color="#7030A0", both=True)
    p.edge(fw, nat, "egress/NAT", color="#BF9000")
    p.edge(bastion, api, "session", color="#2F5597")
    p.edge(sgw, object_storage, "private OSN", color="#4472C4", both=True)

    p.container("Validation matrix", 45, 590, 1710, 510, fill="#F7F7F7", stroke="#A6A6A6")
    headers = ["ID", "Flow", "Expected path", "Controls / expected result"]
    widths = [75, 330, 760, 450]
    x = 75
    for label, width in zip(headers, widths):
        p.box(label, x, 645, width, 45, fill="#4472C4", stroke="#2F5597", font="#FFFFFF", bold=True, rounded=False)
        x += width
    rows = [
        ("1", "Internet → AIMS", "Internet → IGW → Public LB/WAF → Firewall → DRG → Private LB → Traefik", "HTTP 200; firewall traffic log; LB backend healthy"),
        ("2", "AIMS response", "Traefik → Private LB → DRG → Hub ingress RT → Firewall → Public LB → Internet", "Symmetric stateful return; no asymmetric route"),
        ("3", "Pod/worker egress", "OE01 rt-spoke → DRG → Firewall → hub-natgw → Internet", "Source translated by NAT; firewall allows required FQDN/IP"),
        ("4", "Admin → OKE API", "OCI Bastion session → private endpoint 10.1.0.4:6443", "No public API/worker address; IAM + NSG + Kubernetes RBAC"),
        ("5", "OE02 DS → Kafka", "OE02 VCN → DRG → Hub Firewall → DRG → OE01 Kafka TLS/9093", "Inter-OE route only; TLS client auth + Kafka ACL; no DB access"),
        ("6", "OKE → OCI service", "Subnet → Service Gateway → Oracle Services Network", "Private service path; does not require Internet Gateway"),
    ]
    y = 690
    for rid, flow, path, result in rows:
        fill = "#FFFFFF" if int(rid) % 2 else "#EEF3F8"
        vals = [rid, flow, path, result]
        x = 75
        for value, width in zip(vals, widths):
            p.box(value, x, y, width, 62, fill=fill, stroke="#B4C6E7", rounded=False, align="left" if value != rid else "center", size=10, bold=value == rid)
            x += width
        y += 62
    p.footer("Verification evidence: OCI route tables + DRG route rules + firewall traffic/threat logs + VCN flow logs + curl HTTP status • Runtime STOPPED is recorded separately")
    return p.diagram


def intra_oe_page() -> ET.Element:
    p = Page(
        "07 — NET · EW.4 Intra-OE",
        "aims-ew4-intra-oe",
        "AIMS / OCI OPEN LZ — EAST-WEST INTRA-OE",
        "Current shared OKE path versus future cross-VCN path • Adapted from Oracle NET (3) - EW.4 Intra-OE",
    )
    p.container("OE01 • cmp-oe01-development • oe01-vcn 10.1.0.0/16", 65, 175, 1060, 720, fill=COLORS["oe"], stroke=COLORS["oe_stroke"])
    p.container("Shared OKE • VCN-native CNI", 105, 235, 980, 385, fill=COLORS["env"], stroke=COLORS["env_stroke"])
    frontend = p.box("Frontend / API Gateway", 150, 305, 165, 80, fill="#FFFFFF", stroke=COLORS["env_stroke"], bold=True)
    services = p.box("AIMS business services<br>auth • catalog • cart • order<br>payment • inventory • notification", 365, 275, 245, 140, fill="#FFFFFF", stroke=COLORS["env_stroke"], bold=True)
    kafka = p.box("Kafka KRaft ×3<br>TLS/9093 • ACL<br>namespace kafka", 675, 285, 165, 120, fill=COLORS["data"], stroke=COLORS["data_stroke"], bold=True)
    postgres = p.box("PostgreSQL ×3<br>TLS/5432<br>per-service DB/user", 885, 285, 160, 120, fill=COLORS["data"], stroke=COLORS["data_stroke"], bold=True)
    np = p.box("Calico NetworkPolicy<br>default deny + explicit allow", 315, 485, 240, 80, fill="#FFF2CC", stroke="#BF9000", bold=True)
    nsg = p.box("OCI NSG / Security List<br>VCN/subnet boundary", 665, 485, 240, 80, fill="#FFF2CC", stroke="#BF9000", bold=True)
    p.edge(frontend, services, "HTTP", color="#548235", both=True)
    p.edge(services, kafka, "events", color="#7030A0", both=True)
    p.edge(services, postgres, "SQL", color="#7030A0", both=True)
    p.edge(np, services, "L3/L4 policy", color="#BF9000", dashed=True)
    p.edge(nsg, kafka, "subnet/NSG", color="#BF9000", dashed=True)
    p.box(
        "<b>Current path</b><br><br>AIMS ↔ Kafka ↔ PostgreSQL stays inside OKE/oe01-vcn. "
        "It is enforced by Kubernetes NetworkPolicy, Kafka ACL/TLS and database credentials. "
        "It does <b>not</b> traverse DRG or Hub Firewall.",
        130,
        675,
        900,
        135,
        fill="#E2F0D9",
        stroke=COLORS["env_stroke"],
        align="left",
        size=12,
    )

    attach = p.box("OE01 DRG<br>attachment", 930, 535, 120, 65, fill="#DDEBF7", stroke="#2F75B5", bold=True)
    drg = p.box("lz-drg", 1190, 535, 100, 75, fill="#DDEBF7", stroke="#2F75B5", bold=True)
    fw = p.box("Hub B<br>Network Firewall<br>10.0.3.23", 1350, 510, 145, 125, fill=COLORS["danger"], stroke=COLORS["danger_stroke"], bold=True)
    future = p.container("OE01 future environment VCN", 1540, 260, 220, 520, fill="#F2F2F2", stroke="#A6A6A6")
    future_lb = p.box("Private LB", 1570, 515, 160, 60, fill="#FFFFFF", stroke="#A6A6A6")
    future_app = p.box("prod / nonprod workload", 1570, 620, 160, 65, fill="#FFFFFF", stroke="#A6A6A6", bold=True)
    future_db = p.box("private DB/data", 1570, 710, 160, 50, fill="#FFFFFF", stroke="#A6A6A6")
    p.edge(nsg, attach, "future cross-VCN", color="#C00000", dashed=True)
    p.edge(attach, drg, "DRG", color="#C00000", dashed=True)
    p.edge(drg, fw, "inspect", color="#C00000", width=3, both=True)
    p.edge(fw, future_lb, "return", color="#C00000", dashed=True)
    p.edge(future_lb, future_app, "", color="#7F7F7F")
    p.edge(future_app, future_db, "", color="#7F7F7F")
    p.box(
        "<b>Future cross-VCN path</b><br><br>OE01 development → DRG → Hub Firewall → DRG → OE01 prod/nonprod. "
        "Only this intra-OE cross-VCN case needs centralized inspection.",
        1180,
        760,
        540,
        130,
        fill=COLORS["danger"],
        stroke=COLORS["danger_stroke"],
        align="left",
        size=12,
    )
    p.box("Trust boundary 1<br>Kubernetes namespace", 120, 940, 320, 95, fill=COLORS["env"], stroke=COLORS["env_stroke"], bold=True)
    p.box("Trust boundary 2<br>Subnet / NSG / VCN", 480, 940, 320, 95, fill=COLORS["oe"], stroke=COLORS["oe_stroke"], bold=True)
    p.box("Trust boundary 3<br>DRG + centralized firewall", 840, 940, 320, 95, fill=COLORS["danger"], stroke=COLORS["danger_stroke"], bold=True)
    p.box("Data controls<br>TLS • ACL • per-service identity", 1200, 940, 500, 95, fill=COLORS["data"], stroke=COLORS["data_stroke"], bold=True)
    p.footer("Design rule: do not force same-cluster service traffic through an external appliance; inspect only traffic that actually crosses VCN/OE boundaries")
    return p.diagram


def inter_oe_page() -> ET.Element:
    p = Page(
        "08 — NET · EW.3 Inter-OE",
        "aims-ew3-inter-oe",
        "AIMS / OCI OPEN LZ — EAST-WEST INTER-OE",
        "OE02 Data Science consumes approved OE01 services through DRG and Hub Firewall • Adapted from Oracle NET (3) - EW.3 Inter-OE",
    )
    p.container("OE01 • Application platform", 55, 180, 560, 700, fill=COLORS["oe"], stroke=COLORS["oe_stroke"])
    p.text("cmp-oe01-development • oe01-vcn 10.1.0.0/16", 80, 230, 510, 35, size=12, bold=True)
    aims = p.box("AIMS microservices<br>namespace aims", 105, 310, 190, 105, fill=COLORS["env"], stroke=COLORS["env_stroke"], bold=True)
    kafka = p.box("Kafka KRaft ×3<br><b>TLS/9093</b><br>per-client ACL", 345, 300, 200, 125, fill=COLORS["data"], stroke=COLORS["data_stroke"], bold=True)
    pg = p.box("PostgreSQL<br>private only • no OE02 route", 345, 500, 200, 90, fill=COLORS["data"], stroke=COLORS["data_stroke"])
    oe1_nsg = p.box("OE01 NSG<br>allow OE02 CIDR → Kafka:9093 only", 105, 665, 440, 100, fill="#FFF2CC", stroke="#BF9000", bold=True)
    p.edge(aims, kafka, "events", color="#7030A0", both=True)
    p.edge(kafka, pg, "no direct relationship", color="#A6A6A6", dashed=True)

    p.container("Shared Hub B", 660, 180, 480, 700, fill=COLORS["shared"], stroke=COLORS["shared_stroke"])
    drg = p.box("lz-drg<br>separate route tables<br>from-spoke / from-hub", 710, 300, 160, 145, fill="#DDEBF7", stroke="#2F75B5", bold=True)
    fw = p.box("OCI Network Firewall<br><b>aims-hub-b-fw</b><br>10.0.3.23<br>east-west inspection", 920, 285, 170, 175, fill=COLORS["danger"], stroke=COLORS["danger_stroke"], bold=True)
    p.box("No direct VCN peering<br>No transitive bypass", 735, 600, 320, 90, fill="#FFFFFF", stroke=COLORS["shared_stroke"], bold=True)
    p.edge(drg, fw, "route steering", color="#C00000", width=3, both=True)

    p.container("OE02 • Data Science", 1185, 180, 560, 700, fill=COLORS["data"], stroke=COLORS["data_stroke"])
    p.text("cmp-oe02-development • oe02-vcn 10.2.0.0/16", 1210, 230, 510, 35, size=12, bold=True)
    ds = p.box("OCI Data Science<br>Notebook / Job / Model deployment", 1235, 310, 225, 115, fill="#FFFFFF", stroke=COLORS["data_stroke"], bold=True)
    oke_ds = p.box("Optional OKE namespace<br>data-science<br>CPU workload", 1500, 310, 190, 115, fill="#FFFFFF", stroke=COLORS["data_stroke"], dashed=True)
    oe2_nsg = p.box("OE02 NSG<br>egress Kafka:9093 only<br>no PostgreSQL CIDR/port", 1235, 530, 455, 110, fill="#FFF2CC", stroke="#BF9000", bold=True)
    identity = p.box("IAM group: Data Science<br>least privilege in OE02", 1235, 690, 455, 80, fill="#FFFFFF", stroke=COLORS["data_stroke"], bold=True)

    p.edge(kafka, drg, "TLS/9093", color="#C00000", width=3, both=True)
    p.edge(drg, fw, "inspect", color="#C00000", width=3, both=True)
    p.edge(fw, ds, "approved inter-OE flow", color="#C00000", width=3, both=True)
    p.edge(oke_ds, ds, "optional client", color="#7030A0", dashed=True)
    p.edge(oe2_nsg, ds, "egress rule", color="#BF9000", dashed=True)
    p.edge(oe1_nsg, kafka, "ingress rule", color="#BF9000", dashed=True)

    p.container("Inter-OE contract", 115, 925, 1570, 175, fill="#F7F7F7", stroke="#A6A6A6")
    p.box("Allowed", 150, 985, 150, 70, fill="#E2F0D9", stroke=COLORS["env_stroke"], bold=True)
    p.text("OE02 Data Science client → OE01 Kafka TLS/9093 • topic ACL scoped per project • audited through firewall and flow logs", 325, 985, 900, 70, size=12, align="left")
    p.box("Denied", 1250, 985, 140, 70, fill=COLORS["danger"], stroke=COLORS["danger_stroke"], bold=True)
    p.text("OE02 → PostgreSQL/5432, OKE API/6443, worker/pod CIDRs unless separately approved", 1410, 985, 235, 70, size=10, align="left")
    p.footer("OE02 was Terraform-validated as a disposable spoke; this page records the complete target architecture even when OE02 compute is stopped or lab resources are later removed")
    return p.diagram


def posture_page() -> ET.Element:
    p = Page(
        "09 — SEC · Posture",
        "aims-security-posture",
        "AIMS / OCI OPEN LZ — SECURITY POSTURE",
        "Defense in depth across tenancy, edge, network, platform, workload and data • Adapted from Oracle NET (2) - Posture",
    )

    columns = [
        ("1 • EDGE", 45, COLORS["security"], COLORS["security_stroke"], [
            "Regional WAF policy", "Public LB • HTTPS/443", "TLS certificate", "No public OKE API/workers"
        ]),
        ("2 • HUB NETWORK", 365, COLORS["shared"], COLORS["shared_stroke"], [
            "Hub B VCN 10.0.0.0/16", "OCI Network Firewall", "IGW + centralized NAT", "DRG route-table separation"
        ]),
        ("3 • OE NETWORK", 685, COLORS["oe"], COLORS["oe_stroke"], [
            "Private OKE subnets", "NSG + Security Lists", "Service Gateway to OSN", "Bastion for private API"
        ]),
        ("4 • PLATFORM", 1005, COLORS["env"], COLORS["env_stroke"], [
            "OKE RBAC + namespaces", "Calico default-deny", "ResourceQuota / LimitRange", "Signed image digest / GitOps"
        ]),
        ("5 • DATA", 1325, COLORS["data"], COLORS["data_stroke"], [
            "Kafka TLS + ACL", "PostgreSQL per-service identity", "Vault / KMS / Secrets", "Object Storage backup"
        ]),
    ]
    for title, x, fill, stroke, items in columns:
        p.container(title, x, 185, 280, 570, fill=fill, stroke=stroke)
        y = 260
        for item in items:
            p.box(item, x + 25, y, 230, 75, fill="#FFFFFF", stroke=stroke, bold=True if y == 260 else False)
            y += 105

    # Primary traffic path.
    ids = []
    for x, label, fill, stroke in [
        (90, "Internet", "#F2F2F2", "#7F7F7F"),
        (410, "WAF / Public LB", COLORS["security"], COLORS["security_stroke"]),
        (730, "Network Firewall", COLORS["danger"], COLORS["danger_stroke"]),
        (1050, "Private LB / OKE", COLORS["env"], COLORS["env_stroke"]),
        (1370, "AIMS / Kafka / DB", COLORS["data"], COLORS["data_stroke"]),
    ]:
        ids.append(p.box(label, x, 805, 210, 70, fill=fill, stroke=stroke, bold=True))
    for left, right in zip(ids, ids[1:]):
        p.edge(left, right, "", color="#C00000", width=3)

    p.container("Continuous governance and detection", 45, 925, 1560, 185, fill="#F7F7F7", stroke="#7F7F7F")
    controls = [
        ("IAM / Identity Domains", "MFA • least privilege • OE-scoped policy"),
        ("Cloud Guard", "Tenancy target • detector recipes • problems"),
        ("Security Zones", "Maximum recipe for sensitive compartments"),
        ("Logging", "Audit • VCN flow • LB • firewall traffic/threat"),
        ("Operations", "Budgets • alarms • patching • restore drill"),
    ]
    x = 75
    for name, desc in controls:
        p.box(f"<b>{name}</b><br>{desc}", x, 985, 285, 80, fill="#FFFFFF", stroke="#7F7F7F", size=10)
        x += 300
    p.box("Cloud Guard / Logging / Audit span every layer", 1625, 235, 125, 750, fill="#D9E1F2", stroke="#4472C4", bold=True)
    p.footer("Posture shown is the intended complete architecture with firewall. STOPPED compute reduces runtime exposure/cost but does not replace IAM, route, logging or data-protection controls")
    return p.diagram


def _add_oracle_note(diagram: ET.Element, note: str, page_height: int, note_y: int) -> None:
    model = diagram.find("mxGraphModel")
    if model is None:
        raise RuntimeError("Oracle diagram has no mxGraphModel")
    model.set("pageWidth", "1650")
    model.set("pageHeight", str(page_height))
    root = model.find("root")
    if root is None:
        raise RuntimeError("Oracle diagram has no root")
    cell = ET.SubElement(
        root,
        "mxCell",
        {
            "id": f"{diagram.get('id')}-aims-note",
            "value": note,
            "style": (
                "rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF2CC;strokeColor=#D6B656;"
                "fontColor=#7F6000;fontSize=12;fontStyle=1;align=center;verticalAlign=middle;"
                "spacing=8;strokeWidth=2;"
            ),
            "vertex": "1",
            "parent": "1",
        },
    )
    ET.SubElement(
        cell,
        "mxGeometry",
        {"x": "390", "y": str(note_y), "width": "850", "height": "50", "as": "geometry"},
    )


def _plain(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


def clone_oracle_page(
    source_root: ET.Element,
    source_name: str,
    target_name: str,
    target_id: str,
    page_height: int,
    replacements: list[tuple[str, str]],
    *,
    replace_oe_firewalls: bool = False,
    note_y: int = 130,
) -> ET.Element:
    source = next(d for d in source_root.findall("diagram") if d.get("name") == source_name)
    diagram = copy.deepcopy(source)
    diagram.set("name", target_name)
    diagram.set("id", target_id)

    common = [
        ("&lt;region&gt;", "nrt"),
        ("<region>", "nrt"),
        ("frankfurt", "nrt"),
        ("-fra-", "-nrt-"),
        ("_fra_", "_nrt_"),
        ("fra_", "nrt_"),
        ("fra-", "nrt-"),
    ]
    resource_names = [
        ("drg-nrt-hub", "lz-drg"),
        ("192.168.1.10", "10.0.3.23"),
        ("192.168.2.10", "10.0.3.23"),
        ("192.168.1.0/24", "10.0.3.0/24"),
        ("192.168.2.0/24", "10.0.3.0/24"),
        ("192.168.3.0/24", "10.0.4.0/24"),
        ("192.168.4.0/24", "10.0.5.0/24"),
        ("192.168.5.0/24", "10.0.6.0/24"),
        ("10.0.0.0/18", "10.0.0.0/16"),
        ("192.168.0.0/18", "Hub B"),
        ("ig_nrt_hub", "hub-igw"),
        ("ng_nrt_hub", "hub-natgw"),
        ("vcn-nrt-hub", "hub-vcn"),
        ("vcn -nrt-hub", "hub-vcn"),
    ]
    for cell in diagram.findall(".//mxCell"):
        value = cell.get("value")
        if value:
            # Apply region normalization first, then AIMS-specific replacements,
            # and finally generic resource names. This keeps replacement output
            # from being processed a second time (for example AIMS / AIMS).
            for old, new in common:
                value = value.replace(old, new)
            ordered_replacements = sorted(replacements, key=lambda item: len(item[0]), reverse=True)
            normalized = _plain(value)
            for old, new in ordered_replacements:
                if normalized == old:
                    value = new
                    break
            for old, new in ordered_replacements:
                if len(old) > 2:
                    value = value.replace(old, new)
            for old, new in resource_names:
                value = value.replace(old, new)
            cell.set("value", value)

        if replace_oe_firewalls and _plain(cell.get("value", "")) == "Network Firewall":
            geometry = cell.find("mxGeometry")
            x = float(geometry.get("x", "0")) if geometry is not None else 0
            if x > 800:
                cell.set("value", "NSG + NetworkPolicy<br><b>no OE-local firewall</b>")
                cell.set(
                    "style",
                    "rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF2CC;strokeColor=#D6B656;"
                    "fontColor=#7F6000;fontSize=13;fontStyle=1;align=center;verticalAlign=middle;spacing=8;",
                )
            else:
                cell.set("value", "Hub B FW: aims-hub-b-fw · 10.0.3.23")

    _add_oracle_note(
        diagram,
        "AIMS TARGET-STATE • ap-tokyo-1 • Hub B dùng 01 OCI Network Firewall. "
        "OE01/AIMS là hiện thực; OE02/Data Science là spoke đã Terraform-validate. "
        "Compute có thể STOPPED nhưng sơ đồ giữ nguyên kiến trúc đầy đủ trước khi firewall bị xóa.",
        page_height,
        note_y,
    )
    return diagram


def oracle_tailored_pages(source_root: ET.Element) -> list[ET.Element]:
    routing_replacements = [
        ("OCI OPEN LZ - OPERATIONS VIEW - OP.02 MANAGE OPERATING ENTITY - DETAILED VIEW - ROUTING", "AIMS — OE01 ROUTING WITH HUB B FIREWALL"),
        ("vcn -nrt-hub 10.0.0.0/18 192.168.0.0/18", "hub-vcn · Hub B · 10.0.0.0/16"),
        ("vcn -nrt-oe01-dev 172.168.2.0/23", "oe01-vcn · DEVELOPMENT 10.1.0.0/16"),
        ("sn-nrt-oe01-dev-apps 172.168.3.0/25", "sn-oke-pods 10.1.16.0/20"),
        ("sn-nrt-oe01-dev-infra 172.168.2.128/25", "sn-oke-workers 10.1.1.0/24"),
        ("sn-nrt-oe01-dev-lb 172.168.2.0/25", "sn-oke-lb 10.1.2.0/24"),
        ("sn-nrt-oe01-dev-db 172.168.3.128/25", "sn-oke-api 10.1.0.0/28"),
        ("vcn -nrt-oe01-co 172.168.0.0/23", "vcn-oe01-co [FUTURE]"),
        ("vcn -nrt-oe01-np 172.168.4.0/23", "vcn-oe01-np [FUTURE]"),
        ("vcn -nrt-oe01-p 172.168.6.0/23", "vcn-oe01-prod [FUTURE]"),
        ("vcn -nrt-oe01-sb 172.168.8.0/23", "vcn-oe01-sandbox [FUTURE]"),
        ("sn-nrt-hub-fw-ns", "hub-fw-sn · NS"),
        ("sn-nrt-hub-fw-ew", "hub-fw-sn · EW"),
        ("sn-nrt-hub-mgmt", "hub-mgmt-sn"),
        ("sn-nrt-hub-logs", "hub-monitoring-sn"),
        ("sn-nrt-hub-dns", "hub-dns-sn"),
        ("sn-nrt-hub-lb", "hub-publiclb-sn"),
        ("sn-nrt-hub-fw-ew 172.168.0.0/25", "hub-fw-sn · EW 10.0.3.0/24"),
        ("sn-nrt-oe01-p-db 172.168.5.128/25", "sn-nrt-oe01-p-db TBD-PROD-DB"),
        ("sn-nrt-oe01-co-mgmt 1 72.168.0.128/25", "sn-nrt-oe01-co-mgmt TBD-CO-MGMT"),
        ("172.168.2.0/23", "10.1.0.0/16"),
        ("172.168.2.0/25", "10.1.2.0/24"),
        ("172.168.2.128/25", "10.1.1.0/24"),
        ("172.168.3.0/25", "10.1.16.0/20"),
        ("172.168.3.128/25", "10.1.0.0/28"),
        ("172.168.0.0/25", "10.0.3.0/24"),
        ("172.168.0.0/23", "TBD-CO-CIDR"),
        ("172.168.0.128/25", "TBD-CO-MGMT"),
        ("172.168.1.0/25", "TBD-CO-LOGS"),
        ("172.168.1.128/25", "TBD-CO-DNS"),
        ("172.168.4.0/23", "TBD-NONPROD-CIDR"),
        ("172.168.4.0/25", "TBD-NONPROD-LB"),
        ("172.168.4.128/25", "TBD-NONPROD-INFRA"),
        ("172.168.5.0/25", "TBD-NONPROD-APPS"),
        ("172.168.5.128/25", "TBD-NONPROD-DB"),
        ("172.168.6.0/23", "TBD-PROD-CIDR"),
        ("172.168.6.0/25", "TBD-PROD-LB"),
        ("172.168.6.128/25", "TBD-PROD-INFRA"),
        ("172.168.7.0/25", "TBD-PROD-APPS"),
        ("172.168.7.128/25", "TBD-PROD-DB"),
        ("172.168.8.0/23", "TBD-SANDBOX-CIDR"),
        ("172.168.8.0/25", "TBD-SANDBOX-JUMP"),
        ("172.168.8.128/25", "TBD-SANDBOX-A"),
        ("172.168.9.0/25", "TBD-SANDBOX-B"),
        ("172.168.9.128/25", "TBD-SANDBOX-C"),
    ]
    flows_replacements = [
        ("OCI OPEN LZ - OPERATIONS VIEW - DETAILED VIEW - TEST NETWORK FLOWS", "AIMS — TEST NETWORK FLOWS WITH HUB B FIREWALL"),
        ("vcn -nrt-oe01-p 172.168.6.0/23", "oe01-vcn · AIMS · 10.1.0.0/16"),
        ("vcn -nrt-oe01-np 172.168.4.0/23", "oe02-vcn · DATA SCIENCE · 10.2.0.0/16"),
        ("vcn -nrt-hub 10.0.0.0/18 192.168.0.0/18", "hub-vcn · Hub B · 10.0.0.0/16"),
        ("sn-nrt-oe01-p-lb", "sn-oke-lb 10.1.2.0/24"),
        ("sn-nrt-oe01-p-infra", "sn-oke-workers 10.1.1.0/24"),
        ("sn-nrt-oe01-p-apps", "sn-oke-pods 10.1.16.0/20"),
        ("sn-nrt-oe01-p-db", "sn-oke-api 10.1.0.0/28"),
        ("testapp1", "AIMS frontend"),
        ("testapp2", "AIMS API"),
        ("testapp3", "Data Science → Kafka"),
        ("lb-hub-01", "aims-public-lb"),
        ("172.168.6.0/23", "10.1.0.0/16"),
        ("172.168.4.0/23", "10.2.0.0/16"),
        ("172.168.6.63", "10.1.2.145"),
        ("172.168.7.10", "10.1.16.10 (example)"),
        ("172.168.7.11", "10.1.16.11 (example)"),
        ("172.168.5.10", "10.2.1.10 (planned)"),
        ("172.168.4.61", "10.2.2.61 (planned)"),
        ("172.168.6.0/25", "10.1.2.0/24"),
        ("172.168.6.128/25", "10.1.1.0/24"),
        ("172.168.7.0/25", "10.1.16.0/20"),
        ("172.168.5.128/25", "10.1.0.0/28"),
        ("172.168.4.0/25", "10.2.2.0/24"),
        ("172.168.4.128/25", "10.2.1.0/24"),
        ("172.168.5.0/25", "10.2.16.0/20"),
        ("sn-nrt-hub-fw-ns", "hub-fw-sn · NS"),
        ("sn-nrt-hub-fw-ew", "hub-fw-sn · EW"),
        ("sn-nrt-hub-lb", "hub-publiclb-sn"),
    ]
    intra_replacements = [
        ("OCI OPEN LZ - NETWORK VIEW - NETWORK CONNECTIVITY - EAST-WEST INTRA-OE", "AIMS — EAST-WEST INTRA-OE"),
        ("vcn-nrtoe01-co", "OE01 COMMON CONTROLS"),
        ("vcn-nrt-oe01-co", "OE01 COMMON CONTROLS"),
        ("vcn-nrt-oe01-p", "oe01-vcn · DEVELOPMENT · 10.1.0.0/16"),
        ("vcn-nrt-oe01-np", "OE01 NONPROD [FUTURE]"),
        ("vcn-nrt-oe01-dev", "OE01 ADDITIONAL DEV VCN [FUTURE]"),
        ("sn-nrt-oe01-p-lb", "sn-oke-lb · Private LB / Traefik"),
        ("sn-nrt-oe01-p-app", "OKE namespaces · Pods 10.1.16.0/20"),
        ("Proj1 WL Endpoint", "AIMS microservices"),
        ("Proj2 WL Endpoint", "Kafka TLS/9093"),
        ("nsg-nrt- oe01-p-proj1", "Calico policy · AIMS"),
        ("nsg-nrt- oe01-p-proj2", "Kafka ACL + NSG"),
        ("sn-nrt-hub-fw-ns", "hub-fw-sn 10.0.3.0/24"),
        ("nsg-nrt- hub-fw-ns", "hub-fw-nsg"),
        ("Flexible Load Balancer", "Private Load Balancer / Traefik"),
    ]
    inter_replacements = [
        ("OCI OPEN LZ - NETWORK VIEW - NETWORK CONNECTIVITY - EAST-WEST INTER-OE", "AIMS — EAST-WEST INTER-OE"),
        ("vcn-nrtoe01-co", "OE01 COMMON CONTROLS"),
        ("vcn-nrt-oe01-co", "OE01 COMMON CONTROLS"),
        ("vcn-nrt-oe01-p", "oe01-vcn · AIMS · 10.1.0.0/16"),
        ("vcn-nrt-oe01-np", "OE01 NONPROD [FUTURE]"),
        ("vcn-nrt-oe01-dev", "OE01 DEV-2 [FUTURE]"),
        ("vcn-nrtoe02-co", "OE02 COMMON CONTROLS"),
        ("vcn-nrt-oe02-co", "OE02 COMMON CONTROLS"),
        ("vcn-nrt-oe02-p", "oe02-vcn · DATA SCIENCE · 10.2.0.0/16"),
        ("vcn-nrt-oe02-np", "OE02 NONPROD [FUTURE]"),
        ("vcn-nrt-oe02-dev", "OE02 DEV-2 [FUTURE]"),
        ("Proj1 WL Endpoint", "Kafka TLS/9093 endpoint"),
        ("Proj2 WL Endpoint", "OCI Data Science notebook/job"),
        ("Proj3", "Data Science"),
        ("sn-nrt-hub-fw-ew", "hub-fw-sn 10.0.3.0/24"),
        ("nsg-nrt- hub-fw-ew", "hub-fw-nsg"),
        ("Flexible Load Balancer", "Private model endpoint / LB"),
    ]
    posture_replacements = [
        ("OCI OPEN LZ - NETWORK VIEW - NETWORK SECURITY POSTURE", "AIMS — NETWORK SECURITY POSTURE"),
        ("do", ""),
        ("vcn -nrt-hub", "hub-vcn · Hub B · 10.0.0.0/16"),
        ("vcn-nrt-hub", "hub-vcn · Hub B · 10.0.0.0/16"),
        ("vcn -nrt-oe01-co", "OE01 common controls [FUTURE]"),
        ("vcn-nrt-oe01-co", "OE01 common controls [FUTURE]"),
        ("vcn -nrt-oe01-dev", "oe01-vcn · DEVELOPMENT · 10.1.0.0/16"),
        ("vcn-nrt-oe01-dev", "oe01-vcn · DEVELOPMENT · 10.1.0.0/16"),
        ("vcn -nrt-oe01-np", "OE01 NONPROD [FUTURE]"),
        ("vcn-nrt-oe01-np", "OE01 NONPROD [FUTURE]"),
        ("vcn -nrt-oe01-p", "OE01 PROD [FUTURE]"),
        ("vcn-nrt-oe01-p", "OE01 PROD [FUTURE]"),
        ("vcn -nrt-oe01-sb", "OE01 SANDBOX [FUTURE]"),
        ("vcn-nrt-oe01-sb", "OE01 SANDBOX [FUTURE]"),
        ("Central firewall/inspection", "Central Hub B firewall/inspection"),
    ]
    return [
        clone_oracle_page(source_root, "OPS - OE01 Routing", "05 — NET · Routing (Oracle tailored)", "aims-routing", 1320, routing_replacements, note_y=-145),
        clone_oracle_page(source_root, "OPS - Test Network Flows", "06 — OPS · Test Network Flows (Oracle tailored)", "aims-test-network-flows", 1380, flows_replacements, note_y=-145),
        clone_oracle_page(source_root, "NET (3) - EW.4 Intra-OE", "07 — NET · EW.4 Intra-OE (Oracle tailored)", "aims-ew4-intra-oe", 1420, intra_replacements, replace_oe_firewalls=True, note_y=130),
        clone_oracle_page(source_root, "NET (3) - EW.3 Inter-OE", "08 — NET · EW.3 Inter-OE (Oracle tailored)", "aims-ew3-inter-oe", 2140, inter_replacements, replace_oe_firewalls=True, note_y=130),
        clone_oracle_page(source_root, "NET (2) - Posture", "09 — SEC · Posture (Oracle tailored)", "aims-security-posture", 1600, posture_replacements, note_y=90),
    ]


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: update_aims_diagram.py SOURCE_TEMPLATE.drawio TARGET.drawio", file=sys.stderr)
        return 2
    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    if not source.is_file() or not target.is_file():
        raise FileNotFoundError("source template and target workbook must exist")

    # Parse the Oracle source as a guard that the expected reference pages exist.
    source_root = ET.parse(source).getroot()
    source_pages = {d.get("name") for d in source_root.findall("diagram")}
    expected = {
        "OPS - OE01 Routing",
        "OPS - Test Network Flows",
        "NET (3) - EW.4 Intra-OE",
        "NET (3) - EW.3 Inter-OE",
        "NET (2) - Posture",
    }
    missing = expected - source_pages
    if missing:
        raise RuntimeError(f"Oracle reference is missing pages: {sorted(missing)}")

    tree = ET.parse(target)
    root = tree.getroot()
    replacement_ids = {
        "aims-routing",
        "aims-test-network-flows",
        "aims-ew4-intra-oe",
        "aims-ew3-inter-oe",
        "aims-security-posture",
    }
    for diagram in list(root.findall("diagram")):
        if diagram.get("id") in replacement_ids:
            root.remove(diagram)

    for page in oracle_tailored_pages(source_root):
        root.append(copy.deepcopy(page))

    ET.indent(tree, space="  ")
    tree.write(target, encoding="utf-8", xml_declaration=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
