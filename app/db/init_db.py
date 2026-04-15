from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.base import *  # noqa: F401,F403
from app.db.session import SessionLocal, engine
from app.core.config import settings
from app.core.security import hash_password
from app.models.admin import AdminUser
from app.models.base import Base
from app.models.navigation import Menu, MenuItem
from app.models.organization import Contact
from app.models.taxonomy import Language, SiteSetting


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_basics(session)


def seed_basics(session: Session) -> None:
    languages = session.scalars(select(Language)).all()
    if not languages:
        session.add_all(
            [
                Language(code="en", name="English", is_default=True, status="active"),
                Language(code="vi", name="Vietnamese", is_default=False, status="active"),
                Language(code="zh", name="Chinese", is_default=False, status="active"),
            ]
        )

    session.flush()

    language_by_code = {language.code: language for language in session.scalars(select(Language)).all()}
    default_language = language_by_code.get("en") or next(iter(language_by_code.values()))
    default_language_id = default_language.id if default_language else None

    seed_site_settings(session=session, language_id=default_language_id)
    if default_language_id is not None:
        seed_navigation(session=session, language_id=default_language_id)
        seed_contacts(session=session, language_id=default_language_id)
    seed_initial_admin_user(session=session)

    session.commit()


def seed_initial_admin_user(session: Session) -> None:
    existing_admin = session.scalar(select(AdminUser).where(AdminUser.role == "admin"))
    if existing_admin:
        return

    username = settings.initial_admin_username.strip()
    password = settings.initial_admin_password
    if not username or not password:
        return

    session.add(
        AdminUser(
            username=username,
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
        )
    )


def seed_site_settings(session: Session, language_id: int | None) -> None:
    settings_seed = [
        ("site_name", "China Decor", "general", "Public site display name"),
        ("site_tagline", "Corporate Website API", "general", "Short tagline for header/footer"),
        (
            "company_address",
            "Add: 5F, Block C, Hehuamingcheng Building, No.7 Jianguomen South Street, Dongcheng District, Beijing",
            "contact",
            "Company headquarters address",
        ),
        (
            "company_map_url",
            "https://www.openstreetmap.org/export/embed.html?bbox=116.4378%2C39.9087%2C116.4439%2C39.9124&layer=mapnik&marker=39.910466%2C116.44079",
            "contact",
            "Public map embed URL for head office",
        ),
        ("company_phone", "(86)010-65269998", "contact", "Main hotline"),
        ("company_email", "CNDC@sinodecor.com", "contact", "Main contact email"),
        ("copyright_text", "Copyright China Decor", "legal", "Footer copyright line"),
        ("beian_text", "京ICP备12048675号-1", "legal", "备案号"),
        ("beian_url", "https://beian.miit.gov.cn/#/Integrated/index", "legal", "备案跳转地址"),
        ("technical_support_text", "Technical Support: China Decor", "legal", "Footer support text"),
    ]

    settings_by_key = {item.config_key: item for item in session.scalars(select(SiteSetting)).all()}
    now = datetime.now(timezone.utc)

    for config_key, config_value, group_name, description in settings_seed:
        if config_key in settings_by_key:
            record = settings_by_key[config_key]
            record.config_value = config_value
            record.group_name = group_name
            record.description = description
            record.language_id = language_id
            record.updated_at = now
            session.add(record)
            continue

        session.add(
            SiteSetting(
                config_key=config_key,
                config_value=config_value,
                language_id=language_id,
                group_name=group_name,
                description=description,
                updated_at=now,
            )
        )


def seed_contacts(session: Session, language_id: int) -> None:
    existing_contact = session.scalar(
        select(Contact).where(Contact.language_id == language_id).order_by(Contact.is_primary.desc(), Contact.id.asc())
    )
    if existing_contact:
        if not existing_contact.is_primary:
            existing_contact.is_primary = True
            session.add(existing_contact)
        return

    session.add(
        Contact(
            name="China National Decoration Co.,Ltd",
            contact_type="head_office",
            address="5F, Block C, Hehuamingcheng Building, No.7 Jianguomen South Street, Dongcheng District, Beijing",
            postal_code="100005",
            phone="010-65269998",
            email="CNDC@sinodecor.com",
            map_url="https://www.openstreetmap.org/export/embed.html?bbox=116.4378%2C39.9087%2C116.4439%2C39.9124&layer=mapnik&marker=39.910466%2C116.44079",
            latitude="39.910466",
            longitude="116.44079",
            is_primary=True,
            language_id=language_id,
        )
    )


def seed_navigation(session: Session, language_id: int) -> None:
    header_items = [
        {"title": "Home", "url": "/#ctn1", "sort_order": 0},
        {
            "title": "About Us",
            "url": "/about/company-introduction#page1",
            "sort_order": 10,
            "children": [
                {"title": "Company Introduction", "url": "/about/company-introduction#page2", "sort_order": 0},
                {"title": "Chairman's Speech", "url": "/about/chairman-speech#page3", "sort_order": 10},
                {"title": "Organization Chart", "url": "/about/organization-chart#page4", "sort_order": 20},
                {"title": "Corporate Culture", "url": "/about/corporate-culture#page5", "sort_order": 30},
                {"title": "Development Course", "url": "/about/development-course#page6", "sort_order": 40},
                {"title": "Leadership Care", "url": "/about/leadership-care#page7", "sort_order": 50},
                {"title": "Cooperative Partner", "url": "/about/cooperative-partner#page8", "sort_order": 60},
            ],
        },
        {
            "title": "Qualification Honor",
            "url": "/honors",
            "sort_order": 20,
            "children": [
                {"title": "Qualification Certificate", "url": "/honors#page2", "sort_order": 0},
                {"title": "Honorary Awards", "url": "/honors#page3", "sort_order": 10},
            ],
        },
        {
            "title": "Business Display",
            "url": "/business-areas#ctn1",
            "sort_order": 30,
            "children": [
                {"title": "Business Field", "url": "/business-areas#ctn1", "sort_order": 0},
                {"title": "Project Case", "url": "/project-case", "sort_order": 10},
                {"title": "Video", "url": "/video", "sort_order": 20},
            ],
        },
        {
            "title": "News Center",
            "url": "/news/enterprise",
            "sort_order": 40,
            "children": [
                {"title": "Corporate News", "url": "/news/enterprise", "sort_order": 0},
                {"title": "Industry Dynamics", "url": "/news/industry", "sort_order": 10},
            ],
        },
        {
            "title": "Contact Us",
            "url": "/contact",
            "sort_order": 50,
            "children": [
                {"title": "Contact Us", "url": "/contact", "sort_order": 0},
                {"title": "Subsidiary", "url": "/subsidiary", "sort_order": 10},
                {"title": "Branch", "url": "/branch", "sort_order": 20},
                {"title": "Join Us", "url": "/join-us", "sort_order": 30},
            ],
        },
    ]
    footer_items = [
        {
            "title": "About Us",
            "url": "/about/company-introduction#page2",
            "sort_order": 0,
            "children": [
                {"title": "Company Introduction", "url": "/about/company-introduction#page2", "sort_order": 0},
                {"title": "Chairman's Speech", "url": "/about/chairman-speech#page3", "sort_order": 10},
                {"title": "Organization Chart", "url": "/about/organization-chart#page4", "sort_order": 20},
                {"title": "Corporate Culture", "url": "/about/corporate-culture#page5", "sort_order": 30},
                {"title": "Development Course", "url": "/about/development-course#page6", "sort_order": 40},
                {"title": "Leadership Care", "url": "/about/leadership-care#page7", "sort_order": 50},
                {"title": "Cooperative Partner", "url": "/about/cooperative-partner#page8", "sort_order": 60},
            ],
        },
        {
            "title": "Qualification Honor",
            "url": "/honors#page2",
            "sort_order": 10,
            "children": [
                {"title": "Qualification Certificate", "url": "/honors#page2", "sort_order": 0},
                {"title": "Honorary Awards", "url": "/honors#page3", "sort_order": 10},
            ],
        },
        {
            "title": "Business Display",
            "url": "/business-areas#ctn1",
            "sort_order": 20,
            "children": [
                {"title": "Business Field", "url": "/business-areas#ctn1", "sort_order": 0},
                {"title": "Project Case", "url": "/project-case", "sort_order": 10},
                {"title": "Video", "url": "/video", "sort_order": 20},
            ],
        },
        {
            "title": "News Center",
            "url": "/news/enterprise",
            "sort_order": 30,
            "children": [
                {"title": "Corporate News", "url": "/news/enterprise", "sort_order": 0},
                {"title": "Industry Dynamics", "url": "/news/industry", "sort_order": 10},
            ],
        },
        {
            "title": "Social Responsibility",
            "url": "/social-responsibility",
            "sort_order": 40,
        },
        {
            "title": "Contact Us",
            "url": "/contact#ctn2",
            "sort_order": 50,
            "children": [
                {"title": "Contact Us", "url": "/contact#ctn2", "sort_order": 0},
                {"title": "Subsidiary", "url": "/subsidiary#ctn2", "sort_order": 10},
                {"title": "Branch", "url": "/branch", "sort_order": 20},
                {"title": "Join Us", "url": "/join-us", "sort_order": 30},
            ],
        },
    ]

    header_menu = _upsert_menu(
        session=session,
        name="Main Navigation",
        location="header",
        language_id=language_id,
        is_active=True,
    )
    footer_menu = _upsert_menu(
        session=session,
        name="Footer Navigation",
        location="footer",
        language_id=language_id,
        is_active=True,
    )

    _replace_menu_items(session=session, menu=header_menu, nodes=header_items)
    _replace_menu_items(session=session, menu=footer_menu, nodes=footer_items)


def _upsert_menu(session: Session, name: str, location: str, language_id: int, is_active: bool) -> Menu:
    record = session.scalar(
        select(Menu).where(
            Menu.language_id == language_id,
            Menu.location == location,
        )
    )
    if not record:
        record = Menu(name=name, location=location, language_id=language_id, is_active=is_active)
        session.add(record)
        session.flush()
        return record

    record.name = name
    record.is_active = is_active
    session.add(record)
    session.flush()
    return record


def _replace_menu_items(session: Session, menu: Menu, nodes: list[dict], parent_id: int | None = None) -> None:
    if parent_id is None:
        session.execute(delete(MenuItem).where(MenuItem.menu_id == menu.id))
        session.flush()

    for index, node in enumerate(nodes):
        item = MenuItem(
            menu_id=menu.id,
            parent_id=parent_id,
            title=node["title"],
            url=node["url"],
            target=node.get("target"),
            item_type=node.get("item_type"),
            page_id=node.get("page_id"),
            anchor=node.get("anchor"),
            sort_order=node.get("sort_order", index * 10),
        )
        session.add(item)
        session.flush()

        children = node.get("children") or []
        if children:
            _replace_menu_items(session=session, menu=menu, nodes=children, parent_id=item.id)
