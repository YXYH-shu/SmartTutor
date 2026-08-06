"""Seed the active development database with physics learning resources."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "backend" / "app" / "smart_tutor.db"

PHYSICS_RESOURCES = [
    {
        "id": "phys-motion-video-001",
        "name": "匀变速直线运动：位移、速度与加速度",
        "content": "通过速度-时间图像理解匀变速直线运动，练习位移、平均速度和加速度计算。",
        "type": "video",
        "url": "https://www.khanacademy.org/science/physics/one-dimensional-motion",
        "difficult": 0.30,
        "time_need": 18,
        "knowledge_coverage": {"运动学": 1.0, "匀变速直线运动": 1.0},
        "full_score": None,
    },
    {
        "id": "phys-force-sim-002",
        "name": "力与运动：受力分析交互实验",
        "content": "使用交互仿真观察合力、摩擦力和质量改变后物体运动状态的变化。",
        "type": "practice",
        "url": "https://phet.colorado.edu/sims/html/forces-and-motion-basics/latest/forces-and-motion-basics_all.html?locale=zh_CN",
        "difficult": 0.35,
        "time_need": 20,
        "knowledge_coverage": {"牛顿运动定律": 1.0, "受力分析": 1.0, "摩擦力": 0.8},
        "full_score": 20,
    },
    {
        "id": "phys-newton-quiz-003",
        "name": "牛顿运动定律基础测验",
        "content": "十道选择与计算题，检测惯性、合力和牛顿第二定律的掌握情况。",
        "type": "quiz",
        "url": "https://openstax.org/books/college-physics-2e/pages/4-introduction-to-dynamics-newtons-laws-of-motion",
        "difficult": 0.45,
        "time_need": 15,
        "knowledge_coverage": {"牛顿第一定律": 0.8, "牛顿第二定律": 1.0, "牛顿第三定律": 0.8},
        "full_score": 100,
    },
    {
        "id": "phys-energy-sim-004",
        "name": "机械能守恒：能量滑板实验",
        "content": "在无摩擦与有摩擦情境下观察重力势能、动能和热能之间的转化。",
        "type": "practice",
        "url": "https://phet.colorado.edu/sims/html/energy-skate-park-basics/latest/energy-skate-park-basics_all.html?locale=zh_CN",
        "difficult": 0.50,
        "time_need": 22,
        "knowledge_coverage": {"功和能": 0.8, "机械能守恒": 1.0, "能量转化": 1.0},
        "full_score": 20,
    },
    {
        "id": "phys-projectile-video-005",
        "name": "平抛运动与斜抛运动建模",
        "content": "利用分解运动法分析初速度、发射角与落点的关系，并完成参数探究。",
        "type": "video",
        "url": "https://phet.colorado.edu/sims/html/projectile-motion/latest/projectile-motion_all.html?locale=zh_CN",
        "difficult": 0.55,
        "time_need": 25,
        "knowledge_coverage": {"平抛运动": 1.0, "斜抛运动": 1.0, "运动分解": 0.9},
        "full_score": None,
    },
    {
        "id": "phys-circuit-sim-006",
        "name": "直流电路：串并联与欧姆定律",
        "content": "搭建串联和并联电路，测量电压、电流与电阻，验证欧姆定律。",
        "type": "practice",
        "url": "https://phet.colorado.edu/sims/html/circuit-construction-kit-dc/latest/circuit-construction-kit-dc_all.html?locale=zh_CN",
        "difficult": 0.50,
        "time_need": 25,
        "knowledge_coverage": {"电流和电路": 0.9, "欧姆定律": 1.0, "串并联电路": 1.0},
        "full_score": 20,
    },
    {
        "id": "phys-magnetism-article-007",
        "name": "电磁感应与楞次定律导学",
        "content": "从磁通量变化出发理解感应电流方向，并结合发电机原理建立应用联系。",
        "type": "article",
        "url": "https://openstax.org/books/university-physics-volume-2/pages/13-introduction",
        "difficult": 0.70,
        "time_need": 28,
        "knowledge_coverage": {"磁场": 0.7, "电磁感应": 1.0, "楞次定律": 1.0},
        "full_score": None,
    },
    {
        "id": "phys-optics-sim-008",
        "name": "几何光学：凸透镜成像探究",
        "content": "改变物距和焦距，观察实像、虚像、倒立与正立的成像规律。",
        "type": "practice",
        "url": "https://phet.colorado.edu/sims/html/geometric-optics/latest/geometric-optics_all.html?locale=zh_CN",
        "difficult": 0.50,
        "time_need": 20,
        "knowledge_coverage": {"光的折射": 0.8, "凸透镜成像": 1.0, "透镜公式": 0.7},
        "full_score": 20,
    },
    {
        "id": "phys-waves-video-009",
        "name": "机械波：振幅、频率与波速",
        "content": "通过绳波仿真比较波源频率、振幅和介质参数对波形及传播速度的影响。",
        "type": "video",
        "url": "https://phet.colorado.edu/sims/html/wave-on-a-string/latest/wave-on-a-string_all.html?locale=zh_CN",
        "difficult": 0.45,
        "time_need": 18,
        "knowledge_coverage": {"机械波": 1.0, "频率和周期": 0.8, "波速": 1.0},
        "full_score": None,
    },
    {
        "id": "phys-modern-quiz-010",
        "name": "原子物理与光电效应综合练习",
        "content": "综合练习光电效应、能级跃迁和原子结构，适合高中物理选修或复习阶段。",
        "type": "quiz",
        "url": "https://openstax.org/books/university-physics-volume-3/pages/6-introduction",
        "difficult": 0.75,
        "time_need": 24,
        "knowledge_coverage": {"光电效应": 1.0, "原子结构": 0.9, "能级跃迁": 0.8},
        "full_score": 100,
    },
]

PHYSICS_KNOWLEDGE_POINTS = [
    {
        "id": "kp-phys-kinematics-001",
        "name": "匀变速直线运动",
        "content": "理解位移、速度、加速度及其图像关系，并能完成基础计算。",
        "difficult": 0.30,
        "cognitive_level": "理解",
    },
    {
        "id": "kp-phys-force-002",
        "name": "受力分析与牛顿运动定律",
        "content": "能够识别物体所受重力、支持力、拉力和摩擦力，并依据合力判断运动状态。",
        "difficult": 0.35,
        "cognitive_level": "应用",
    },
    {
        "id": "kp-phys-newton-laws-003",
        "name": "牛顿运动定律",
        "content": "掌握牛顿第一、第二、第三定律及其在简单动力学问题中的应用。",
        "difficult": 0.45,
        "cognitive_level": "应用",
    },
    {
        "id": "kp-phys-energy-004",
        "name": "机械能守恒",
        "content": "理解动能、重力势能和机械能守恒条件，能分析能量转化过程。",
        "difficult": 0.50,
        "cognitive_level": "应用",
    },
    {
        "id": "kp-phys-projectile-005",
        "name": "平抛与斜抛运动",
        "content": "使用运动分解法分析平抛和斜抛运动的位移、速度及轨迹。",
        "difficult": 0.55,
        "cognitive_level": "应用",
    },
    {
        "id": "kp-phys-circuits-006",
        "name": "欧姆定律与串并联电路",
        "content": "掌握电流、电压、电阻关系，并能分析串联与并联电路。",
        "difficult": 0.50,
        "cognitive_level": "应用",
    },
    {
        "id": "kp-phys-induction-007",
        "name": "电磁感应与楞次定律",
        "content": "理解磁通量变化、感应电流方向和楞次定律的基本应用。",
        "difficult": 0.70,
        "cognitive_level": "分析",
    },
    {
        "id": "kp-phys-optics-008",
        "name": "凸透镜成像",
        "content": "掌握物距、像距和焦距关系，判断凸透镜的成像性质。",
        "difficult": 0.50,
        "cognitive_level": "应用",
    },
    {
        "id": "kp-phys-waves-009",
        "name": "机械波与波速",
        "content": "理解振幅、频率、周期和波速的物理意义及其关系。",
        "difficult": 0.45,
        "cognitive_level": "理解",
    },
    {
        "id": "kp-phys-modern-010",
        "name": "光电效应与原子物理",
        "content": "理解光电效应、原子能级和能级跃迁的基本规律。",
        "difficult": 0.75,
        "cognitive_level": "分析",
    },
]

RESOURCE_KNOWLEDGE_LINKS = [
    ("phys-motion-video-001", "kp-phys-kinematics-001"),
    ("phys-force-sim-002", "kp-phys-force-002"),
    ("phys-newton-quiz-003", "kp-phys-newton-laws-003"),
    ("phys-energy-sim-004", "kp-phys-energy-004"),
    ("phys-projectile-video-005", "kp-phys-projectile-005"),
    ("phys-circuit-sim-006", "kp-phys-circuits-006"),
    ("phys-magnetism-article-007", "kp-phys-induction-007"),
    ("phys-optics-sim-008", "kp-phys-optics-008"),
    ("phys-waves-video-009", "kp-phys-waves-009"),
    ("phys-modern-quiz-010", "kp-phys-modern-010"),
]


def seed(database_path: Path) -> tuple[int, int, int, int, int, int]:
    database_path = database_path.resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"Database not found: {database_path}")

    insert_sql = """
        INSERT INTO learning_resources (
            id, name, content, type, url, difficult, time_need,
            knowledge_coverage, embed, full_score, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO NOTHING
    """
    insert_knowledge_point_sql = """
        INSERT INTO knowledge_points (
            id, name, content, subject, grade, pre_knowledge, parent_knowledge,
            standard, difficult, embed, grade_level, cognitive_level, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO NOTHING
    """
    insert_resource_knowledge_sql = """
        INSERT INTO resource_knowledge (resource_id, kp_id)
        VALUES (?, ?)
        ON CONFLICT(resource_id, kp_id) DO NOTHING
    """

    inserted_resources = 0
    inserted_knowledge_points = 0
    inserted_links = 0
    with sqlite3.connect(database_path) as connection:
        for resource in PHYSICS_RESOURCES:
            cursor = connection.execute(
                insert_sql,
                (
                    resource["id"],
                    resource["name"],
                    resource["content"],
                    resource["type"],
                    resource["url"],
                    resource["difficult"],
                    resource["time_need"],
                    json.dumps(resource["knowledge_coverage"], ensure_ascii=False),
                    None,
                    resource["full_score"],
                ),
            )
            inserted_resources += cursor.rowcount

        for knowledge_point in PHYSICS_KNOWLEDGE_POINTS:
            cursor = connection.execute(
                insert_knowledge_point_sql,
                (
                    knowledge_point["id"],
                    knowledge_point["name"],
                    knowledge_point["content"],
                    "物理",
                    "高中",
                    None,
                    None,
                    "高中物理",
                    knowledge_point["difficult"],
                    None,
                    "高中",
                    knowledge_point["cognitive_level"],
                ),
            )
            inserted_knowledge_points += cursor.rowcount

        for resource_id, knowledge_point_id in RESOURCE_KNOWLEDGE_LINKS:
            cursor = connection.execute(
                insert_resource_knowledge_sql, (resource_id, knowledge_point_id)
            )
            inserted_links += cursor.rowcount

        resource_total = connection.execute(
            "SELECT COUNT(*) FROM learning_resources"
        ).fetchone()[0]
        knowledge_point_total = connection.execute(
            "SELECT COUNT(*) FROM knowledge_points"
        ).fetchone()[0]
        link_total = connection.execute(
            "SELECT COUNT(*) FROM resource_knowledge"
        ).fetchone()[0]

    return (
        inserted_resources,
        inserted_knowledge_points,
        inserted_links,
        resource_total,
        knowledge_point_total,
        link_total,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help=f"SQLite database path (default: {DEFAULT_DATABASE})",
    )
    args = parser.parse_args()
    (
        inserted_resources,
        inserted_knowledge_points,
        inserted_links,
        resource_total,
        knowledge_point_total,
        link_total,
    ) = seed(args.database)
    print(
        "Inserted "
        f"resources={inserted_resources}, knowledge_points={inserted_knowledge_points}, "
        f"resource_knowledge_links={inserted_links}. "
        "Totals: "
        f"resources={resource_total}, knowledge_points={knowledge_point_total}, "
        f"resource_knowledge_links={link_total}."
    )


if __name__ == "__main__":
    main()
