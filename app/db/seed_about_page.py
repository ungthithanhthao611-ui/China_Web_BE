"""
Sprint 2 – Seed About page CMS data.

Tạo 1 page canonical slug="about" với đầy đủ:
- 8 page_sections
- 20 content_blocks
- ~100+ content_block_items

Dữ liệu lấy thẳng từ AboutPage.vue hard-code.
Thiết kế idempotent: chạy lại không tạo duplicate.
"""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.content import ContentBlock, ContentBlockItem, Page, PageSection


# ---------------------------------------------------------------------------
# Helpers – idempotent get-or-create
# ---------------------------------------------------------------------------

def _get_or_create_page(session: Session, slug: str, language_id: int, **kwargs) -> Page:
    page = session.scalar(
        select(Page).where(Page.slug == slug, Page.language_id == language_id)
    )
    if not page:
        page = Page(slug=slug, language_id=language_id)
    for k, v in kwargs.items():
        setattr(page, k, v)
    session.add(page)
    session.flush()
    return page


def _get_or_create_section(session: Session, page_id: int, anchor: str, **kwargs) -> PageSection:
    section = session.scalar(
        select(PageSection).where(
            PageSection.page_id == page_id,
            PageSection.anchor == anchor,
        )
    )
    if not section:
        section = PageSection(page_id=page_id, anchor=anchor)
    for k, v in kwargs.items():
        setattr(section, k, v)
    session.add(section)
    session.flush()
    return section


def _get_or_create_block(
    session: Session,
    entity_type: str,
    entity_id: int,
    block_key: str,
    language_id: int | None,
    **kwargs,
) -> ContentBlock:
    filters = [
        ContentBlock.entity_type == entity_type,
        ContentBlock.entity_id == entity_id,
        ContentBlock.block_key == block_key,
    ]
    if language_id is not None:
        filters.append(
            or_(ContentBlock.language_id == language_id, ContentBlock.language_id.is_(None))
        )
    else:
        filters.append(ContentBlock.language_id.is_(None))

    block = session.scalar(select(ContentBlock).where(*filters))
    if not block:
        block = ContentBlock(
            entity_type=entity_type,
            entity_id=entity_id,
            block_key=block_key,
            language_id=language_id,
        )
    for k, v in kwargs.items():
        setattr(block, k, v)
    session.add(block)
    session.flush()
    return block


def _get_or_create_item(session: Session, block_id: int, item_key: str, **kwargs) -> ContentBlockItem:
    item = session.scalar(
        select(ContentBlockItem).where(
            ContentBlockItem.block_id == block_id,
            ContentBlockItem.item_key == item_key,
        )
    )
    if not item:
        item = ContentBlockItem(block_id=block_id, item_key=item_key)
    for k, v in kwargs.items():
        setattr(item, k, v)
    session.add(item)
    session.flush()
    return item


# ---------------------------------------------------------------------------
# Image base URLs (same as AboutPage.vue)
# ---------------------------------------------------------------------------
_IMG_BASE = "https://en.sinodecor.com/portal-local/ngc202304190002/cms/image"
_REPO_BASE = "https://en.sinodecor.com/repository/portal-local/ngc202304190002/cms/image"


def _img(f: str) -> str:
    return f"{_IMG_BASE}/{f}"


def _repo(f: str) -> str:
    return f"{_REPO_BASE}/{f}"


# ---------------------------------------------------------------------------
# Main seed function
# ---------------------------------------------------------------------------

def seed_about_page(session: Session, language_id: int) -> None:
    """Seed About page with all sections, blocks, and items."""

    # ── 1. Page ────────────────────────────────────────────────────────────
    about = _get_or_create_page(
        session,
        slug="about",
        language_id=language_id,
        title="About Us",
        summary="China National Decoration Co., LTD. – Integrated design, construction, and delivery for premium spaces since 1984.",
        body=None,
        page_type="about",
        parent_id=None,
        status="published",
        meta_title="About Us | China Decor",
        meta_description="Learn about China Decor – company introduction, chairman's speech, organization, corporate culture, development history, leadership care, and cooperative partners.",
        sort_order=5,
    )
    pid = about.id

    # ── 2. Sections ────────────────────────────────────────────────────────
    sections_seed = [
        ("hero", "About Hero", "hero", 10),
        ("company_introduction", "Company Introduction", "content", 20),
        ("chairman_speech", "Chairman's Speech", "content", 30),
        ("organization_chart", "Organization Chart", "media", 40),
        ("corporate_culture", "Corporate Culture", "content", 50),
        ("development_course", "Development Course", "timeline", 60),
        ("leadership_care", "Leadership Care", "gallery", 70),
        ("cooperative_partner", "Cooperative Partner", "partners", 80),
    ]
    for anchor, title, section_type, sort_order in sections_seed:
        _get_or_create_section(
            session,
            page_id=pid,
            anchor=anchor,
            title=title,
            section_type=section_type,
            sort_order=sort_order,
            content=None,
            image_id=None,
        )

    # ── 3 & 4. Blocks + Items ─────────────────────────────────────────────
    _seed_hero_blocks(session, pid, language_id)
    _seed_intro_blocks(session, pid, language_id)
    _seed_speech_blocks(session, pid, language_id)
    _seed_org_chart_blocks(session, pid, language_id)
    _seed_culture_blocks(session, pid, language_id)
    _seed_timeline_blocks(session, pid, language_id)
    _seed_leadership_blocks(session, pid, language_id)
    _seed_partner_blocks(session, pid, language_id)


# ===========================================================================
# Block + Item seeders per section
# ===========================================================================

def _seed_hero_blocks(session: Session, page_id: int, lang_id: int) -> None:
    # hero_summary
    b = _get_or_create_block(
        session, "page", page_id, "hero_summary", lang_id,
        title="About Hero Summary", block_type="key_value", sort_order=10,
    )
    _get_or_create_item(session, b.id, "headline",
                        title="ABOUT US", sort_order=10)
    _get_or_create_item(session, b.id, "description",
                        title="Hero description",
                        content="This golden signboard - China Decoration embodies the efforts and accumulation of several generations of people from China Decoration.",
                        sort_order=20)

    # hero_nav
    b = _get_or_create_block(
        session, "page", page_id, "hero_nav", lang_id,
        title="About Navigation Tabs", block_type="nav_list", sort_order=20,
    )
    nav_items = [
        ("company_introduction", "Company Introduction"),
        ("chairman_speech", "Chairman's Speech"),
        ("organization_chart", "Organization Chart"),
        ("corporate_culture", "Corporate Culture"),
        ("development_course", "Development Course"),
        ("leadership_care", "Leadership Care"),
        ("cooperative_partner", "Cooperative Partner"),
    ]
    for idx, (key, label) in enumerate(nav_items):
        _get_or_create_item(
            session, b.id, key,
            title=label,
            sort_order=(idx + 1) * 10,
            metadata_json={"target_anchor": key},
        )


def _seed_intro_blocks(session: Session, page_id: int, lang_id: int) -> None:
    # intro_media
    b = _get_or_create_block(
        session, "page", page_id, "intro_media", lang_id,
        title="Company Introduction Media", block_type="media", sort_order=30,
    )
    _get_or_create_item(session, b.id, "cover_image",
                        title="Company introduction cover",
                        sort_order=10,
                        metadata_json={"src": _img("f1225086-4996-4f1d-88f9-08f4228a378e.png")})

    # intro_video
    b = _get_or_create_block(
        session, "page", page_id, "intro_video", lang_id,
        title="Company Introduction Video", block_type="video", sort_order=40,
    )
    _get_or_create_item(session, b.id, "video_button",
                        title="VIDEO +", sort_order=10)
    _get_or_create_item(session, b.id, "video_url",
                        title="Company intro video",
                        link="/images/vd/1fb59345-a995-4408-b03b-e8e38ff258e7.web.mp4",
                        sort_order=20)

    # intro_paragraphs
    paragraphs = [
        "China National Decoration Co., LTD. (hereinafter referred to as 'China Decoration') was established in 1984 with the approval of the State Economic Commission and the Ministry of Light Industry. It is the first batch of large-scale and high-grade decoration enterprises with Grade A qualification of indoor and outdoor building decoration construction and design. Large-scale cross-regional, cross-industry digital assembly type construction joint-stock decoration backbone enterprises.",
        "China decoration takes 'innovative industry model, leading green development, and decorating a better life' as the enterprise mission. Adhere to the development path of meeting market demand, highlighting the characteristics of the company, and gathering force to innovate and build. The company now has architectural decoration engineering professional contracting level I, architectural decoration engineering professional design Grade A, exhibition exhibition engineering design and construction integration level I, exhibition engineering level I, museum exhibition exhibition design grade A, museum exhibition exhibition construction level I, building curtain wall, electronics and intelligence, building mechanical and electrical installation, steel structure, ancient buildings, building engineering construction general contracting, special engineering (structural reinforcement) and other professional qualifications.",
        "Forty years of development, China Decoration has always adhered to the deep cultivation of architectural decoration design and construction of the decoration industry. Through years of business practice, China Decoration has set up a dual headquarters development base in Beijing and East China, set up a 'design research institute and ten management centers' and a structure model of multiple functional departments, and set up 7 design branches, 7 branches and 9 subsidiaries nationwide, with a large number of industry experts and technical talents.",
        "Under the leadership of the Party committee and the board of directors of the company, China Decoration adheres to the corporate values of 'winning respect by character, improving happiness by quality, creating value by brand', and has always been in a leading position in the architectural decoration industry with strong professional strength and innovation ability. It has successively been rated as 'Top 100 enterprises in China's building decoration industry', 'National Building Decoration Award Star Enterprise', 'quality and trustworthy enterprise', 'enterprise credit evaluation AAA level credit enterprise', 'Top Ten most influential brands in China's decoration industry', 'Best design Enterprise of the Year' and 'National high-tech Enterprise'.",
        "In the process of development, China Decoration insists on fulfilling its corporate social responsibility, devoting itself to charity undertakings for a long time, continuously donating money to various public welfare organizations, including Beihang Education Foundation, Beijing Red Cross Society, Beijing New Sunshine Charity Foundation, China Children and Youth Foundation, and carrying out activities such as claiming green space and earthquake donations, with a total donation amount of more than 30 million yuan.",
        "In the new era of opportunities, China Decoration takes building domestic first-class intelligent technology, digital design, assembly and construction enterprises as the starting point and goal. It has formed a layout plan of 'building decoration design and construction as the core, digital design as the technical support, vocational education as the talent support, ecological environment, intelligent construction, assembly integration, green new energy materials four plates go hand in hand', creating the development pattern of China's decoration industry chain and promoting the transformation and upgrading of the company.",
    ]
    b = _get_or_create_block(
        session, "page", page_id, "intro_paragraphs", lang_id,
        title="Company Introduction Text", block_type="rich_text_list", sort_order=50,
    )
    for idx, text in enumerate(paragraphs):
        _get_or_create_item(
            session, b.id, f"paragraph_{idx + 1}",
            title=None,
            content=text,
            sort_order=(idx + 1) * 10,
        )


def _seed_speech_blocks(session: Session, page_id: int, lang_id: int) -> None:
    # speech_profile
    b = _get_or_create_block(
        session, "page", page_id, "speech_profile", lang_id,
        title="Chairman Portrait", block_type="media", sort_order=60,
    )
    _get_or_create_item(session, b.id, "portrait",
                        title="Chairman portrait",
                        sort_order=10,
                        metadata_json={"src": "/images/4e3ee279-9a2c-4021-8fbf-ce7c9aefc218.jpg"})

    # speech_body
    speech_paragraphs = [
        "Ladies and Gentlemen:\nThank leaders, colleagues and partners for their long-term support and love!",
        "Forty years of trials and hardships is a magnificent history of struggle, but also a song of vigorous development. China Decoration Co., Ltd. from the early establishment of the reform and opening up to the growth and growth of the new century, all the way difficult, all the way bumpy, through an extraordinary development process. However, we always maintain the enthusiasm and reverence for the industry, uphold the quality concept of 'artisan spirit, the pursuit of quality', and cast quality models, which has won wide recognition and high praise from all walks of life.",
        "We have always been convinced that 'excellence, pioneering and innovation' is the fundamental way for enterprises to occupy a leading position in the market, 'let every project become a high-quality project' is our ultimate pursuit of technological achievements, but also hidden in the quality of the company's profound brand. After years of precipitation and accumulation, China Decoration has developed into a cross-regional, cross-industry large-scale joint-stock building decoration enterprise, in the design technology, industrial structure, service mode, management ideas, brand quality, personnel training and other aspects of continuous innovation, continue to stimulate the new vitality of the industry, input new momentum for the market, and cultivate a large number of new professionals.",
        "New quality productivity, leading the development of science and technology for China's building decoration industry to open the door of digitalization and intelligence. In the process of transformation and upgrading of the company, we firmly implement the new development concept, open the journey of high-quality development, focus on the application of new technologies, new materials, new processes and new equipment, practice the concept of innovation and green, promote the integration of industry and technology, and help China achieve the goal of 'double carbon', in order to create the greatest value for customers. Return the support and trust of the community to us.",
        "The ancient great event, not only exceptional talent, but also perseverance. In the face of opportunities and challenges in the new era, China Decoration will continue to carry the mission of the times, break through the inherent barriers of the industry, open up a broader space for development, and keep up with the pace of the times. It will further promote the low-carbon transformation in the field of building decoration, digital transformation, intelligent assembly interior integrated decoration, intelligent construction, and the rapid development of new building industrialization, and become the leader and developer of China's building decoration industry.",
        "We sincerely invite all partners to pursue their dreams, create a better space, and write a new chapter for the development of the field of architectural decoration in our country.",
    ]
    b = _get_or_create_block(
        session, "page", page_id, "speech_body", lang_id,
        title="Chairman's Speech Text", block_type="rich_text_list", sort_order=70,
    )
    for idx, text in enumerate(speech_paragraphs):
        _get_or_create_item(
            session, b.id, f"paragraph_{idx + 1}",
            title=None,
            content=text,
            sort_order=(idx + 1) * 10,
        )

    # speech_signature
    b = _get_or_create_block(
        session, "page", page_id, "speech_signature", lang_id,
        title="Chairman Signature", block_type="key_value", sort_order=80,
    )
    _get_or_create_item(session, b.id, "sign_title",
                        title="Chairman of China Decoration Co., LTD.",
                        sort_order=10)
    _get_or_create_item(session, b.id, "sign_name",
                        title="Xin Jianlin",
                        sort_order=20)
    _get_or_create_item(session, b.id, "signature_image",
                        title="Signature image",
                        sort_order=30,
                        metadata_json={"src": "/images/5ea063cc-18de-4c5c-8e82-3fb04d11f038.png"})


def _seed_org_chart_blocks(session: Session, page_id: int, lang_id: int) -> None:
    b = _get_or_create_block(
        session, "page", page_id, "org_chart_image", lang_id,
        title="Organization Chart", block_type="media", sort_order=90,
    )
    _get_or_create_item(session, b.id, "main_chart",
                        title="Organization chart image",
                        sort_order=10,
                        metadata_json={"src": _img("bcb4ff12-813e-43ef-9669-e5ed2da9a123.png")})


def _seed_culture_blocks(session: Session, page_id: int, lang_id: int) -> None:
    culture_data = [
        (
            "culture_purpose", "Corporate Purpose", 100,
            [
                ("Customer satisfaction", "All the value of China Decoration comes from customers; without customers, there is nothing."),
                ("Make employees proud", "Employee growth is the realistic foundation of the company's value."),
                ("Let the world recognize", "Excellent enterprises must have a deep global strategic vision and international thinking, keep an open mind, and promote enterprises to internationalization."),
            ],
        ),
        (
            "culture_mission", "Corporate Mission", 110,
            [
                ("Innovative industry model", "The company welcomes change with a positive attitude, regards change as the biggest development opportunity, embraces the trend of digitalization, industrialization and intelligence, and innovates the industry development model."),
                ("Leading the green development", "Actively explore the ecological science and technology business field, promote the development of circular economy, promote the construction of ecological civilization and high-level protection of the ecological environment, and help achieve the goal of carbon peak and carbon neutrality."),
                ("Decorate a better life", "We are committed to making every member of society learn, work and live in an elegant and comfortable environment, and enjoy the fun of life."),
            ],
        ),
        (
            "culture_spirit", "Enterprise Spirit", 120,
            [
                ("Creating value", "Creating value is fundamental to the survival and development of China Decoration."),
                ("Innovation and development", "Innovation and development is the core of the overall development of China Decoration. It is the first driving force for the development of China Decoration, advocating and practicing design technology, industrial structure, service mode, management ideas, brand quality and talent training innovation."),
                ("Entrepreneurship is more than", "The best defense is offense, the best defense is entrepreneurship."),
            ],
        ),
        (
            "culture_values", "Value", 130,
            [
                ("Character to win respect", "People have quality, the root in the lattice, the emphasis on virtue."),
                ("Quality to improve happiness", "To create diversified products and create a high quality of life is the meaning and value of people in China Decoration."),
                ("Brand creation value", "The Chinese decorative national-name golden signboard condensed generations of people in 40 years of painstaking efforts, operations and management and value accumulation."),
            ],
        ),
    ]
    for block_key, block_title, sort_order, items in culture_data:
        b = _get_or_create_block(
            session, "page", page_id, block_key, lang_id,
            title=block_title, block_type="bullet_list", sort_order=sort_order,
        )
        for idx, (label, text) in enumerate(items):
            _get_or_create_item(
                session, b.id, f"item_{idx + 1}",
                title=label,
                content=text,
                sort_order=(idx + 1) * 10,
            )


def _seed_timeline_blocks(session: Session, page_id: int, lang_id: int) -> None:
    timeline_entries = [
        (1984, 9, 'The company was approved to be established as "China Indoor Complete Sets Corporation"', ""),
        (1985, 11, "The company undertook the first five-star hotel decoration project - Friendship Hotel project", _img("6d13d208-48e9-4b73-aee5-c356fa97ca03.jpg")),
        (1989, 12, "The company held the first interior decoration exhibition in Beijing", _img("610aa7c0-9b72-44a2-bda2-48afb495ee95.jpg")),
        (1992, 12, "Held the inauguration meeting of China Interior Decoration Complete Sets Group in the Great Hall of the People", _img("a481f2e2-5e24-4f0f-90d0-ef1a93986f03.jpg")),
        (1995, 12, "The Party committee of the company held a party member meeting", _img("50808b66-5056-4c17-9ce9-c9fe80f31ca6.jpg")),
        (1996, 12, "The company's office building has been completed", ""),
        (1997, 9, "The company was renamed China Decoration (Group) Company", ""),
        (2003, 1, "The first reform of China Decoration, registered by the State Administration for Industry and Commerce as China Decoration Co., LTD", ""),
        (2009, 6, "The Henan Art Center project that the company participated in won the Luban Award of China Construction Engineering", ""),
        (2009, 10, "The company presents to the 60th birthday of the motherland through the Tian'anmen LED display system", _img("3b800d78-091f-41b3-a57f-a6584ab2c64a.jpg")),
        (2010, 12, "The company name is changed to China Decoration Co., LTD", ""),
        (2011, 12, "Established Yangzhou Yangzijiang China Decoration Building Decoration Engineering Co., LTD., a joint venture with Yangzhou Yangzijiang Group", ""),
        (2014, 12, 'The company held the 30th anniversary celebration of "Collection Glory Flying Dream" at the National Convention Center', _img("c6e0ed19-2885-4752-a334-9255baa8257b.jpg")),
        (2015, 5, "Li Jiefeng, the former chairman of the company, was elected president and secretary-general of Beijing Architectural Decoration Association", ""),
        (2016, 6, "The company passed the national high-tech enterprise identification", _img("f031b874-f982-4b1b-9ec2-9060a03e18a6.jpg")),
        (2020, 6, "Xin Jianlin, the third chairman of the company, took over from China Decoration and set up a new executive team", _img("0f422b10-759a-4f1c-9ca7-43f739047ed8.jpg")),
        (2025, 1, 'The Company Held a "Create and Fight for the Future" 40th Anniversary Celebration at the Beijing International Hotel Conference Center', _img("238a2ef1-f15e-4758-bd09-8167e7a86216.jpg")),
    ]

    b = _get_or_create_block(
        session, "page", page_id, "timeline", lang_id,
        title="Development Course Timeline", block_type="timeline", sort_order=140,
    )
    for idx, (year, month, title, image_url) in enumerate(timeline_entries):
        meta = {"year": year, "month": month}
        if image_url:
            meta["image_url"] = image_url
        _get_or_create_item(
            session, b.id, f"milestone_{idx + 1}",
            title=title,
            sort_order=(idx + 1) * 10,
            metadata_json=meta,
        )


def _seed_leadership_blocks(session: Session, page_id: int, lang_id: int) -> None:
    leadership_items = [
        (
            "1985",
            _img("6aafd3c9-4a3a-41d5-a585-5dd2a437a92f.png"),
            "The former minister of light industry Yang Bo (right fourth) in early 1985 personally visited my company to undertake the completion of the friendship hotel decoration site market condolences.",
        ),
        (
            "1995",
            _img("227db1de-3a33-435f-8a68-6e4a10c7ac85.png"),
            "The former president of the National Light Industry Federation Yu Zhen (left) and the relevant leaders of the ministries and commissions visited the company in person and guided the work in the conference room of the original rented office building.",
        ),
        (
            "2001",
            _img("63c5ff0a-119e-4573-864a-e45630fa1185.png"),
            "The former president of the National Light Industry Association Chen Shineng (fourth from right) visited the company to inspect and guide the work, accompanied by the former company leader Wei Kun (third from right).",
        ),
        (
            "2011",
            _img("4dcf4307-673a-4386-b351-7dcdbf31dc05.png"),
            "Ma Tinggui, President of China Building Decoration Association (second from left) visited the company to inspect and guide the work.",
        ),
        (
            "2011b",
            _img("e40a3fbe-4ba1-434c-9ae3-11f28e77e7ab.png"),
            "China Light Industry Federation President Bo Zhengfa, Vice President Tao Xiaonian, China Interior Decoration Association President Liu Yu, Secretary General Zhang Li and other leading comrades visited the company to inspect and guide the work.",
        ),
    ]

    b = _get_or_create_block(
        session, "page", page_id, "leadership_care_gallery", lang_id,
        title="Leadership Care Gallery", block_type="gallery", sort_order=150,
    )
    for idx, (year, image_url, text) in enumerate(leadership_items):
        _get_or_create_item(
            session, b.id, f"visit_{idx + 1}",
            title=text,
            sort_order=(idx + 1) * 10,
            metadata_json={"year": year, "image_url": image_url},
        )


def _seed_partner_blocks(session: Session, page_id: int, lang_id: int) -> None:
    # partner_categories
    b = _get_or_create_block(
        session, "page", page_id, "partner_categories", lang_id,
        title="Partner Categories", block_type="tab_list", sort_order=160,
    )
    categories = [
        ("strategic_cooperation", "Strategic Cooperation"),
        ("business_cooperation", "Business Cooperation"),
        ("institutional_cooperation", "Institutional Cooperation"),
        ("industry_associations", "Industry Associations"),
    ]
    for idx, (key, label) in enumerate(categories):
        _get_or_create_item(
            session, b.id, key,
            title=label,
            sort_order=(idx + 1) * 10,
        )

    # partner_logos
    b = _get_or_create_block(
        session, "page", page_id, "partner_logos", lang_id,
        title="Partner Logos", block_type="logo_grid", sort_order=170,
    )

    logos = [
        # Strategic Cooperation
        ("strategic_01", "http://www.shlinli.com/", _img("6370e615-d83c-43d2-ac61-da5d37ef3a23.jpg"), "strategic_cooperation"),
        ("strategic_02", "https://www.avic.com/", _img("b7dfe5e0-0484-44e2-8f1c-7ed1cf732672.jpg"), "strategic_cooperation"),
        ("strategic_03", "http://www.ntscid.com/", _img("b09df614-1954-45d7-9e72-2b943e91e032.jpg"), "strategic_cooperation"),
        ("strategic_04", "https://www.chinaso.com/", _img("bd7988af-2dda-4fc4-ba81-0aa2c46e1138.png"), "strategic_cooperation"),
        ("strategic_05", "https://www.bucg.com/", _img("5b360838-195b-417c-b9f5-c2729c6963b0.gif"), "strategic_cooperation"),
        ("strategic_06", "http://www.ccd.com.hk/", _img("5ef29600-187a-45e8-9990-5bc337249164.png"), "strategic_cooperation"),
        ("strategic_07", "http://www.hxwy.com.cn/", _img("79e2da0c-9570-4450-8766-303eb9d872c6.png"), "strategic_cooperation"),
        ("strategic_08", "https://www.az.com.cn/", _img("fd157699-2f31-43c8-a27d-f7bb51c050ca.png"), "strategic_cooperation"),
        ("strategic_09", "http://www.ideapool.tv/", _img("502cf951-2835-4ce4-97c7-e9dcc0b6cd87.png"), "strategic_cooperation"),
        ("strategic_10", "http://www.jiusi.net/", _img("2417ee26-0ef5-4c04-bc30-d8fdd9fc22f3.png"), "strategic_cooperation"),
        # Business Cooperation
        ("business_01", "http://www.10086.cn/bj/", _img("c07f7c3b-4b9c-49a7-add4-d6b7d5311c1e.png"), "business_cooperation"),
        ("business_02", "https://www.chd.com.cn/", _img("0829ee1d-40be-48bb-8add-3b20cc94f11f.png"), "business_cooperation"),
        ("business_03", "https://www.cnooc.com.cn/", _img("7bdcdf66-291d-48b7-8ad4-25b5e67ad981.png"), "business_cooperation"),
        ("business_04", "https://www.fosun.com/", _img("f144ac96-87d3-4a3d-b0fa-7e031dca7f5b.png"), "business_cooperation"),
        ("business_05", "http://www.cnpc.com.cn/", _img("58260315-6796-4d66-b84f-f655415b62fd.png"), "business_cooperation"),
        ("business_06", "http://www.cofco.com/cn/", _img("072c99df-dc7f-4363-9bec-272c60402238.png"), "business_cooperation"),
        ("business_07", "http://www.wanda.cn/", _img("4127f235-c134-4c81-96d8-356a23257058.png"), "business_cooperation"),
        ("business_08", "https://www.cfldcn.com/", _img("df21f2d8-be81-48da-899a-4cd1c087f94c.png"), "business_cooperation"),
        ("business_09", "http://www.spic.com.cn/", _img("5ecfab36-8675-40c8-a47e-84a3a4086d89.png"), "business_cooperation"),
        ("business_10", "https://www.gemdale.com/", _img("54310c5d-720a-4910-8d78-1662f39d508c.png"), "business_cooperation"),
        ("business_11", "https://www.sunac.com.cn/", _img("00ab262b-eacb-4eaf-9c94-af6f9c7cfd43.png"), "business_cooperation"),
        ("business_12", "http://www.bankofbeijing.com.cn", _img("bfd1c647-ea0d-4f7c-9eea-fdf1ff06c17f.png"), "business_cooperation"),
        ("business_13", "http://www.ccb.com/cn/home/indexv3.html", _img("ac28702e-28fd-4476-979b-70bc431bd038.png"), "business_cooperation"),
        ("business_14", "http://www.abchina.com/cn/", _img("86ed3568-8b26-4355-8738-a1606647c10d.png"), "business_cooperation"),
        ("business_15", "http://www.icbc.com.cn/icbc/", _img("c89e54dc-54d9-433b-86ea-12daedd33f46.png"), "business_cooperation"),
        # Institutional Cooperation
        ("institutional_01", "https://www.tsinghua.edu.cn/", _img("3967f2e4-4b28-4f06-8fed-d83b00787f43.png"), "institutional_cooperation"),
        ("institutional_02", "https://www.sg.pku.edu.cn/", _img("d89e4819-0071-4bf4-be69-3381c6027929.png"), "institutional_cooperation"),
        ("institutional_03", "http://www.buaa.edu.cn/", _img("f2325055-bddd-41df-a965-da871f0f78d7.png"), "institutional_cooperation"),
        ("institutional_04", "http://www.neu.edu.cn/", _img("fcc283b9-dd76-4103-84a0-602c1190eba4.png"), "institutional_cooperation"),
        ("institutional_05", "https://www.yzjsxy.com/", _img("5b670d41-92f8-44db-947b-78944ebcc82a.png"), "institutional_cooperation"),
        # Industry Associations
        ("association_01", "http://www.cida.org.cn/", _img("adb7b287-e16d-447b-a130-4bafc4b1d371.png"), "industry_associations"),
        ("association_02", "http://www.cbda.cn/", _img("a93c78ed-bb1f-4f89-94d4-ddb8cb1cbbfe.gif"), "industry_associations"),
        ("association_03", "https://www.chinamuseum.org.cn/", _img("57325a61-ee56-490a-b89c-90e2c56f647e.png"), "industry_associations"),
        ("association_04", "http://www.bcda.org.cn/", _img("9ee5b030-ea8b-4887-9244-186dd43a50ef.png"), "industry_associations"),
        ("association_05", "http://www.caec.org.cn/", _img("8ee0eaaf-d284-4cdc-914b-8c77f7732e49.png"), "industry_associations"),
        ("association_06", "http://www.jszszx.com.cn/", _img("339748f8-51e2-4090-8873-2ebb97fa0c29.png"), "industry_associations"),
    ]

    for idx, (item_key, website, image_url, category) in enumerate(logos):
        _get_or_create_item(
            session, b.id, item_key,
            title=None,
            link=website,
            sort_order=(idx + 1) * 10,
            metadata_json={"category": category, "image_url": image_url, "website": website},
        )
