"""
Dynamic Skill Router (`0.8 * Cosine + 0.2 * BM25`) & Builtin Skill Loader for workbuddy-cli.
Directly ports `Bm25Index` and `RecallIndex` from WorkBuddyAI's `recall_service_rag.js`,
and integrates the enhanced `skill-creator` (`init_skill.py`, `quick_validate.py`, `package_skill.py`).
"""

import hashlib
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from .config import ASSETS_DIR


TOKEN_REGEX = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+")
LOCAL_EMBED_DIM = 256


def tokenize(text: str) -> List[str]:
    if not text:
        return []
    return [m.group(0).lower() for m in TOKEN_REGEX.finditer(text)]


def compute_local_embedding(text: str, dim: int = LOCAL_EMBED_DIM) -> List[float]:
    """
    Deterministic local 256-dim L2-normalized feature embedding (Signed Feature Hashing over
    unigrams, CJK bigrams, and English character trigrams) when no remote `/v1/embeddings`
    endpoint is configured (since DeepSeek official API does not expose `/v1/embeddings`).
    Ensures `0.8 * Cosine + 0.2 * BM25` always computes real non-zero cosine similarity!
    """
    toks = tokenize(text)
    if not toks:
        return [0.0] * dim

    features: List[Tuple[str, float]] = []
    for i, t in enumerate(toks):
        # Unigram feature (higher weight)
        features.append((f"u:{t}", 1.5))
        # Bigram feature for phrase/compound matching (e.g. 红头, 公文, 公式, 重算)
        if i + 1 < len(toks):
            features.append((f"b:{t}_{toks[i + 1]}", 2.0))
        # Character 3-grams for English subword resilience (e.g. docx, recalc, xlsx)
        if len(t) >= 3 and t.isascii():
            for j in range(len(t) - 2):
                features.append((f"c3:{t[j : j + 3]}", 0.8))

    vec = [0.0] * dim
    for feat, weight in features:
        h = hashlib.md5(feat.encode("utf-8")).digest()
        bucket = ((h[0] << 8) | h[1]) % dim
        sign = 1.0 if (h[2] & 1) == 0 else -1.0
        vec[bucket] += sign * weight

    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0.0:
        vec = [v / norm for v in vec]
    return vec


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class Bm25Index:
    """Exact port of WorkBuddy's `Bm25Index` (`k1 = 1.5, b = 0.75`)."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs: List[Dict[str, Any]] = []
        self.df: Dict[str, int] = {}
        self.avg_doc_length: float = 0.0

    def build(self, items: List[Dict[str, str]]) -> None:
        self.docs = []
        self.df.clear()
        total_len = 0
        for item in items:
            tokens = tokenize(item.get("text", ""))
            tf: Dict[str, int] = {}
            for tok in tokens:
                tf[tok] = tf.get(tok, 0) + 1
            for tok in set(tokens):
                self.df[tok] = self.df.get(tok, 0) + 1
            self.docs.append(
                {
                    "id": item["id"],
                    "tokens": tokens,
                    "tf": tf,
                    "length": len(tokens),
                }
            )
            total_len += len(tokens)
        self.avg_doc_length = (total_len / len(self.docs)) if self.docs else 0.0

    def score(self, query: str) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        q_tokens = tokenize(query)
        if not q_tokens or not self.docs:
            return scores
        n_docs = len(self.docs)
        avg_len = self.avg_doc_length or 1.0
        for doc in self.docs:
            doc_score = 0.0
            for tok in q_tokens:
                tf = doc["tf"].get(tok, 0)
                if not tf:
                    continue
                df = self.df.get(tok, 0)
                idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
                denom = tf + self.k1 * (1.0 - self.b + self.b * (doc["length"] / avg_len))
                doc_score += idf * (tf * (self.k1 + 1.0)) / denom
            if doc_score > 0.0:
                scores[doc["id"]] = doc_score
        return scores

    @staticmethod
    def normalize(scores: Dict[str, float]) -> Dict[str, float]:
        if not scores:
            return {}
        max_val = max(scores.values())
        if max_val <= 0.0:
            return dict(scores)
        return {k: v / max_val for k, v in scores.items()}


@dataclass
class SkillItem:
    id: str
    name: str
    description: str
    file_path: Path
    tags: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    vector: Optional[List[float]] = None

    def recall_text(self) -> str:
        lines = [f"skill: {self.name}", self.description]
        if self.examples:
            lines.append("examples: " + " / ".join(self.examples))
        if self.tags:
            lines.append("tags: " + " / ".join(self.tags))
        return "\n".join(lines)


class RecallIndex:
    """
    Exact port of WorkBuddy's `RecallIndex`:
    `score = 0.8 * cosine + 0.2 * bm25` (with automatic pure-BM25 fallback when vectors are absent).
    """

    def __init__(self, embedding_weight: float = 0.8):
        self.embedding_weight = embedding_weight
        self.items: List[SkillItem] = []
        self.bm25 = Bm25Index()

    def rebuild(self, items: List[SkillItem]) -> None:
        self.items = list(items)
        self.bm25.build([{"id": it.id, "text": it.recall_text()} for it in self.items])

    def upsert(self, item: SkillItem) -> None:
        for idx, existing in enumerate(self.items):
            if existing.id == item.id:
                self.items[idx] = item
                break
        else:
            self.items.append(item)
        self.bm25.build([{"id": it.id, "text": it.recall_text()} for it in self.items])

    def search(
        self,
        query: str,
        query_vector: Optional[List[float]] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        if not self.items:
            return []
        raw_bm25 = self.bm25.score(query)
        norm_bm25 = Bm25Index.normalize(raw_bm25)
        has_vec = bool(query_vector and len(query_vector) > 0)
        w = self.embedding_weight

        results = []
        for item in self.items:
            cos_val = (
                max(0.0, cosine_similarity(query_vector, item.vector))
                if (has_vec and item.vector)
                else 0.0
            )
            bm25_val = norm_bm25.get(item.id, 0.0)
            final_score = (w * cos_val + (1.0 - w) * bm25_val) if (has_vec and item.vector) else bm25_val
            if final_score > 0.0:
                results.append(
                    {
                        "id": item.id,
                        "name": item.name,
                        "description": item.description,
                        "score": round(final_score, 4),
                        "cosine": round(cos_val, 4),
                        "bm25": round(bm25_val, 4),
                        "file_path": str(item.file_path),
                    }
                )
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]


class SkillRouter:
    """Loads all reversed WorkBuddy builtin skills and routes user queries dynamically."""

    def __init__(self, skills_dir: Optional[Path] = None):
        self.skills_dir = Path(skills_dir) if skills_dir else (ASSETS_DIR / "skills")
        self.index = RecallIndex(embedding_weight=0.8)
        self.skills_by_id: Dict[str, SkillItem] = {}
        self.load_builtin_skills()

    def load_builtin_skills(self) -> List[SkillItem]:
        catalog = [
            SkillItem(
                id="workbuddy-office-routing",
                name="workbuddy-office-routing",
                description="Word/Excel/PPT 办公文档总路由：拦截报告/总结/演讲稿/公文请求，默认路由至三阶段 HTML->Docx 排版流水线",
                file_path=self.skills_dir / "workbuddy-office-routing.md",
                tags=["word", "docx", "office", "报告", "总结", "演讲稿", "排版"],
                examples=["帮我写一份季度总结报告", "生成一份项目汇报 Word 文档"],
            ),
            SkillItem(
                id="tdoc-orchestrator",
                name="tdoc-orchestrator",
                description="三阶段 Word 文档编排器（Stage 1 doc-writer 写 md -> Stage 2 doc-formatter 排 HTML -> Stage 3 doc-converter 转 docx），默认推荐原地 [角色切换] 零损耗模式",
                file_path=self.skills_dir / "tdoc-orchestrator.md",
                tags=["docx", "word", "角色切换", "封面", "目录", "html-to-doc"],
                examples=["把这篇 Markdown 排成带封面和目录的 Word 文档"],
            ),
            SkillItem(
                id="doc-typeset-government-doc",
                name="doc-typeset-government-doc",
                description="GB/T 9704-2012 国家标准党政机关红头公文排版规范（26pt #cc0000 红头、发文字号、签发人、一/（一）/1./（1）顶格层级、公文页码）",
                file_path=self.skills_dir / "doc-typeset-government-doc.md",
                tags=["红头公文", "红头文件", "通知", "通报", "请示", "GB/T 9704", "党政公文"],
                examples=["起草一份关于安全生产检查的红头通知公文", "生成符合 GB/T 9704 标准的红头文件"],
            ),
            SkillItem(
                id="doc-typeset-base",
                name="doc-typeset-base",
                description="HTML 转 Word 核心排版规范：禁止裸色值/裸字号、修复封面『模 拟 人 生 4』两端对齐继承 Bug、禁止 span 伪装 badge",
                file_path=self.skills_dir / "doc-typeset-base.md",
                tags=["html", "css", "排版", "封面居中", "review_html"],
                examples=["检查 HTML 排版是否符合转 Word 门禁规范"],
            ),
            SkillItem(
                id="sheet-recalc",
                name="sheet-recalc",
                description="Excel (.xlsx) 公式三层重算与 GB 45438-2025 AIGC 隐式水印打标：回填 <v> 缓存节点，彻底解决 openpyxl 公式在微信/手机预览空白痛点",
                file_path=self.skills_dir / "sheet_recalc.py",
                tags=["excel", "xlsx", "公式", "recalc", "微信预览空白", "SUM", "openpyxl"],
                examples=["重算这张 Excel 表格里的公式缓存", "生成带公式计算结果的财务报表 xlsx"],
            ),
            SkillItem(
                id="critic-generator-engine",
                name="critic-generator-engine",
                description="六步对抗式盲审引擎（Isolate 剥离思维链 -> LoadRubrics 延迟加载尺规 -> Score -> Challenge 强制扣分配额 min_issues=2, min_instructions=3 -> Decide -> Report）",
                file_path=self.skills_dir / "critic-generator-engine.md",
                tags=["盲审", "审查", "critic", "挑刺", "审稿", "强制扣分", "review"],
                examples=["对这篇技术方案做对抗式盲审挑刺", "用 Critic 引擎审查报告质量"],
            ),
            SkillItem(
                id="workbuddy-finance-skill",
                name="workbuddy-finance-skill",
                description="金融投研与量化分析 Skill：A股红涨绿跌、一句话检索防子代理发散铁律、跨市场财年对齐（阿里4月/苹果9月/微软7月）、缠论/波浪/DCF 量化分析",
                file_path=self.skills_dir / "workbuddy-finance-skill.md",
                tags=["金融", "股票", "A股", "研报", "估值", "DCF", "缠论", "财报", "K线"],
                examples=["分析 A 股某公司的财务数据与估值", "生成一份股票投研报告"],
            ),
            SkillItem(
                id="geo-map-compliance-guard",
                name="geo-map-compliance-guard",
                description="中国地图合规护栏：严禁使用 Google Maps / OpenStreetMap，强制使用 GCJ-02 坐标系与腾讯地图 GL JS，严格规范中国台湾与南海诸岛标注",
                file_path=self.skills_dir / "geo-map-compliance-guard.md",
                tags=["地图", "GIS", "坐标", "GCJ-02", "腾讯地图", "合规"],
                examples=["在网页里画一张门店分布地图", "生成中国各省数据可视化地图"],
            ),
            SkillItem(
                id="expert-team-manager",
                name="expert-team-manager",
                description="专家团与角色切换规范（含齐活林/许清楚/高见远/寇豆码/严过关谐音花名规范，以及推荐的单上下文 [角色切换] 模式）",
                file_path=self.skills_dir / "expert-team-spec.md",
                tags=["专家团", "expert", "team", "角色切换", "齐活林", "寇豆码"],
                examples=["用软件公司专家团模式设计并实现功能", "列出内置专家团"],
            ),
            SkillItem(
                id="skill-creator",
                name="skill-creator",
                description="技能创建器与打包校验工具：支持 init_skill.py 初始化（含 agent_created: true）、quick_validate.py 资源引用审计与 package_skill.py 打包",
                file_path=self.skills_dir / "skill-creator" / "SKILL.md",
                tags=["skill", "创建技能", "插件", "打包", "validate"],
                examples=["帮我创建一个新的自定义 Skill", "校验并打包我的技能目录"],
            ),
        ]

        # Also scan custom skills if any exist in skills_dir
        for sub in sorted(self.skills_dir.iterdir()) if self.skills_dir.exists() else []:
            if sub.is_dir() and sub.name != "skill-creator":
                skill_md = sub / "SKILL.md"
                if skill_md.exists():
                    text = skill_md.read_text(encoding="utf-8")
                    desc_m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
                    desc = desc_m.group(1).strip() if desc_m else f"Custom skill {sub.name}"
                    catalog.append(
                        SkillItem(
                            id=sub.name,
                            name=sub.name,
                            description=desc,
                            file_path=skill_md,
                            tags=["custom", sub.name],
                        )
                    )

        for item in catalog:
            if not item.vector:
                item.vector = compute_local_embedding(item.recall_text())

        self.skills_by_id = {item.id: item for item in catalog}
        self.index.rebuild(catalog)
        return catalog

    def match(
        self,
        query: str,
        query_vector: Optional[List[float]] = None,
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        q_vec = query_vector if query_vector is not None else compute_local_embedding(query)
        return self.index.search(query, query_vector=q_vec, top_k=top_k)

    def load_skill_content(self, skill_id: str, max_chars: int = 12000) -> str:
        item = self.skills_by_id.get(skill_id)
        if not item or not item.file_path.exists():
            return ""
        return item.file_path.read_text(encoding="utf-8")[:max_chars]

    def build_matched_skills_prompt(self, query: str, top_k: int = 2) -> str:
        matches = self.match(query, top_k=top_k)
        if not matches:
            return ""
        blocks = ["<recalled_skills>"]
        for m in matches:
            sid = m["id"]
            score = m["score"]
            content = self.load_skill_content(sid, max_chars=6000)
            blocks.append(
                f'### Skill: {sid} (Recall Score: {score}, BM25: {m["bm25"]}, Cosine: {m["cosine"]})\n{content}'
            )
        blocks.append("</recalled_skills>")
        return "\n\n".join(blocks)
