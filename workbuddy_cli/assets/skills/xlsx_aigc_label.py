#!/usr/bin/env python3
"""给本地生成的 xlsx 写入 AIGC 隐式标识（GB 45438-2025 /《人工智能生成合成内容标识办法》）。

标识写进 `docProps/custom.xml` 的 `AIGC` 自定义属性，值为紧凑 JSON。字段集合、字段顺序、
取值含义都按 CSIG 的隐式标识规范（iWiki 4015184282「隐式标识实现方案」+ 4015001661
「AIGC内容标注概览」）——该规范的格式定义就是
`{"AIGC":{"Label":…,"ContentProducer":…,"ProduceID":…,"ReservedCode1":…,
"ContentPropagator":…,"PropagateID":…,"ReservedCode2":…}}`，且明确把 XLSX 列为支持格式。

其中**两个预留码字段本地链路留空**（按规范的空值省略规则不写进 XML），所以本地产物比线上
导出少这两个字段，其余字段的名称、顺序、取值口径完全一致；留空的理由见 `build_payload`，
对完整性判据的影响见 `is_complete`。ProduceID 缺省是随机生成的唯一编码，
`ContentProducer` 按 `--platform` 取该链路的编码（云端与本地包各一个，见模块顶部常量）。

用法：
    python3 aigc_label.py <file.xlsx> --platform DESKTOP   # 写入标识
    python3 aigc_label.py <file.xlsx> --check              # 只查验，未打标则非零退出

建表脚本是每次由模型现写的，产物必然是从零生成、不可能已带标识，所以这里不做「已有标识
则跳过/升级」的判断：一律按当前参数写入，重复执行结果一致。
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

# 生成合成服务提供者编码（规范要求 27 位）。**两条链路各一个，不互相对齐**（2026-09-27 裁定）：
#   - 云端：交付物是导入后的在线表格，本地 xlsx 只是中间产物，标识由后端 aigclabel 链路写，
#     用的就是 docx-online `labelsdk.TDocsContentProducer` 那个编码 —— 即 CLOUD_CONTENT_PRODUCER。
#   - 本地包（WORKBUDDY / DESKTOP）：本地 xlsx 直接交付，由本脚本打标，用 LOCAL_CONTENT_PRODUCER。
# 所以看到两个编码不一致是**设计如此**，不是漂移；换编码是接入单的事，各自改自己那个。
CLOUD_CONTENT_PRODUCER = "00119144030071526726XG1QI7W"
LOCAL_CONTENT_PRODUCER = "00119111010856365494821B355"

# 按平台取编码。CLOUD_AGENT 之外（含未标注平台）一律按本地包处理 —— 本脚本只会进本地
# 平台的产物：`docx-ai/src/sheet/scripts/build.mjs` 的 PLATFORM_EXCLUDED_PATHS 把
# aigc_label.py 排除在 CLOUD_AGENT 之外。
PRODUCER_BY_PLATFORM = {"CLOUD_AGENT": CLOUD_CONTENT_PRODUCER}


def producer_for_platform(platform=None):
    """取该平台的生成合成服务提供者编码；未指定/未知平台按本地包口径。"""
    key = (platform or "").strip().upper()
    return PRODUCER_BY_PLATFORM.get(key, LOCAL_CONTENT_PRODUCER)

# 规范取值：1=属于人工智能生成合成，2=可能为，3=疑似为。整份由模型生成的表恒为 1。
LABEL_AI_GENERATED = "1"

PROPERTY_NAME = "AIGC"

CUSTOM_NS = "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
VT_NS = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

CUSTOM_PART = "docProps/custom.xml"
CUSTOM_CT = "application/vnd.openxmlformats-officedocument.custom-properties+xml"
CUSTOM_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties"
)
# 自定义属性固定 fmtid，OOXML 规定值
FMTID = "{D5CDD505-2E9C-101B-9397-08002B2CF9AE}"


def build_payload(produce_id=None, content_producer=None, platform=None):
    """构建标识 JSON。

    字段集合与顺序按规范给出的格式定义（iWiki 4015001661），空值字段省略。生产者角色下
    传播者三个字段镜像生产者字段。

    `content_producer` 显式给定则用它；否则按 `platform` 取该链路的编码（见模块顶部
    两个常量与 `producer_for_platform`）。

    ProduceID 规范里定义为「产研自行生成的内容唯一编码，用于溯源」，这里缺省取随机 UUID：
    能保证唯一，但无法反查到是哪次会话生成的。要做到会话级溯源得由运行时把 trace id 注入
    进来（skill 脚本拿不到会话信息），已另行记录待议。

    **预留码留空。** 规范（iWiki 4015184282）把 `ReservedCode1` / `ReservedCode2` 定义为
    「用于保护内容、标识完整性的信息」，官方算法 `GenProducerReserveCode` 要传接入单发放的
    `PrivateKey` 和 `KeyVersion`；私钥不能随插件分发到用户机器，所以本地生成链路算不出
    可验签的预留码。填一个本地随机密钥加密、密钥用完即弃的值，在构造上就不可能被任何人
    校验，只是让字段看起来非空——留空比填这种值更诚实，也不给检测侧制造「像是有效预留码」
    的假象。
    """
    produce_id = produce_id or uuid.uuid4().hex
    producer = content_producer or producer_for_platform(platform)
    fields = [
        ("Label", LABEL_AI_GENERATED),
        ("ContentProducer", producer),
        ("ProduceID", produce_id),
        ("ReservedCode1", ""),
        # 生产者角色：传播者编码/编号与生产者相同
        ("ContentPropagator", producer),
        ("PropagateID", produce_id),
        ("ReservedCode2", ""),
    ]
    return json.dumps(
        {k: v for k, v in fields if v != ""},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def read_label(path):
    """读回文件里已有的 AIGC 标识值；没有则返回 None。"""
    try:
        with zipfile.ZipFile(path) as zf:
            if CUSTOM_PART not in zf.namelist():
                return None
            root = ET.fromstring(zf.read(CUSTOM_PART))
    except (zipfile.BadZipFile, ET.ParseError, KeyError):
        return None
    for prop in root.findall(f"{{{CUSTOM_NS}}}property"):
        if prop.get("name") == PROPERTY_NAME:
            node = prop.find(f"{{{VT_NS}}}lpwstr")
            return node.text if node is not None else None
    return None


def is_complete(label):
    """标识的生产者要素是否齐全。

    按 Label + ContentProducer + ProduceID 三项判。规范把生产者三要素连 `ReservedCode1`
    一起列为必需项（后端 `isAllProduceLabelComplete` 就是按四项判的），但本地链路拿不到
    私钥、预留码按裁定留空（见 `build_payload`），所以这里不把它算进必需项——否则 `--check`
    永远判 unlabeled，交付被自己的关卡挡死。

    影响面：若检测侧照后端那份四项逻辑实现，本地产物会被判为标识不完整。
    这一条已在报告里如实标出。
    """
    if not label:
        return False
    try:
        data = json.loads(label)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(data, dict):
        return False
    return all(data.get(k) for k in ("Label", "ContentProducer", "ProduceID"))


def _next_pid(root):
    """自定义属性 pid 从 2 起、必须唯一。"""
    pids = [int(p.get("pid", 1)) for p in root.findall(f"{{{CUSTOM_NS}}}property")]
    return max(pids + [1]) + 1


def _custom_xml_with_label(existing_bytes, payload):
    """在既有 custom.xml 上写入 AIGC 属性；没有既有内容则新建。

    openpyxl 会把 `wb.properties.title` 之类写进 docProps/core.xml，custom.xml 则只有
    用了 custom_doc_props 才有；两种情况都要能处理，且不能动别的自定义属性。
    """
    ET.register_namespace("", CUSTOM_NS)
    ET.register_namespace("vt", VT_NS)
    if existing_bytes:
        root = ET.fromstring(existing_bytes)
        for prop in root.findall(f"{{{CUSTOM_NS}}}property"):
            if prop.get("name") == PROPERTY_NAME:
                root.remove(prop)
    else:
        root = ET.Element(f"{{{CUSTOM_NS}}}Properties")
    prop = ET.SubElement(
        root,
        f"{{{CUSTOM_NS}}}property",
        {"fmtid": FMTID, "pid": str(_next_pid(root)), "name": PROPERTY_NAME},
    )
    ET.SubElement(prop, f"{{{VT_NS}}}lpwstr").text = payload
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + ET.tostring(
        root, encoding="utf-8"
    )


def _content_types_with_custom(data):
    """确保 [Content_Types].xml 声明 custom.xml 的 Override，否则 Excel 视为包损坏。"""
    ET.register_namespace("", CT_NS)
    root = ET.fromstring(data)
    for ov in root.findall(f"{{{CT_NS}}}Override"):
        if ov.get("PartName") == f"/{CUSTOM_PART}":
            return ET.tostring(root, encoding="utf-8", xml_declaration=True)
    ET.SubElement(
        root,
        f"{{{CT_NS}}}Override",
        {"PartName": f"/{CUSTOM_PART}", "ContentType": CUSTOM_CT},
    )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _rels_with_custom(data):
    """确保 _rels/.rels 引用 custom.xml —— 未被任何 .rels 引用的 part 属于游离部件。"""
    ET.register_namespace("", RELS_NS)
    root = ET.fromstring(data)
    ids = set()
    for rel in root.findall(f"{{{RELS_NS}}}Relationship"):
        if rel.get("Target") in (CUSTOM_PART, f"/{CUSTOM_PART}"):
            return ET.tostring(root, encoding="utf-8", xml_declaration=True)
        ids.add(rel.get("Id"))
    n = 1
    while f"rId{n}" in ids:
        n += 1
    ET.SubElement(
        root,
        f"{{{RELS_NS}}}Relationship",
        {"Id": f"rId{n}", "Type": CUSTOM_REL_TYPE, "Target": CUSTOM_PART},
    )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def stamp(path, payload):
    """把标识写进 OOXML 包。

    逐 part 原样复制、只改必要的三个 part，这样重算回填的缓存值、样式、图表都不受影响；
    写临时文件后 os.replace 原子替换，中途失败不会留下半个损坏的交付物。
    """
    path = Path(path)
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        contents = {n: zf.read(n) for n in names}

    contents[CUSTOM_PART] = _custom_xml_with_label(contents.get(CUSTOM_PART), payload)
    if "[Content_Types].xml" in contents:
        contents["[Content_Types].xml"] = _content_types_with_custom(
            contents["[Content_Types].xml"]
        )
    if "_rels/.rels" in contents:
        contents["_rels/.rels"] = _rels_with_custom(contents["_rels/.rels"])

    order = names + [n for n in contents if n not in names]
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".aigc-tmp")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for name in order:
                zout.writestr(name, contents[name])
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main():
    ap = argparse.ArgumentParser(description="为本地生成的 xlsx 写入 AIGC 隐式标识")
    ap.add_argument("file", help="xlsx 绝对路径")
    ap.add_argument("--produce-id", default=None, help="内容制作编号，缺省随机生成")
    ap.add_argument("--content-producer", default=None, help="生成合成服务提供者编码，覆盖平台取值")
    ap.add_argument(
        "--platform",
        default=None,
        help="构建平台（CLOUD_AGENT / WORKBUDDY / DESKTOP），决定用哪个服务提供者编码",
    )
    ap.add_argument("--check", action="store_true", help="只查验不写入")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.is_file():
        print(json.dumps({"error": f"file not found: {path}"}, ensure_ascii=False))
        return 1
    if not zipfile.is_zipfile(path):
        print(json.dumps({"error": f"not an OOXML package: {path}"}, ensure_ascii=False))
        return 1

    if args.check:
        label = read_label(path)
        complete = is_complete(label)
        print(
            json.dumps(
                {
                    "status": "labeled" if complete else "unlabeled",
                    "label": label,
                },
                ensure_ascii=False,
            )
        )
        return 0 if complete else 1

    try:
        payload = build_payload(args.produce_id, args.content_producer, args.platform)
        stamp(path, payload)
    except Exception as exc:  # noqa: BLE001 - 失败要让调用方看到原因
        print(json.dumps({"error": f"stamp failed: {exc}"}, ensure_ascii=False))
        return 1

    written = read_label(path)
    if written != payload:
        print(
            json.dumps(
                {"error": "verification read-back mismatch", "label": written},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"status": "labeled", "label": payload}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
