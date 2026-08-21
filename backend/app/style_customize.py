"""
OZELLESTIR: EMBEDDING/LLM TABANLI STIL PROFILI ESLESTIRME
-----------------------------------------------------------
style_engine.py'deki icerik-tabanli (kelime agirlikli, if-else
zinciri) skorlamadan BILINCLI OLARAK FARKLI bir yol.

Burada "renk == siyah ise X goster" gibi statik bir kural yok.
Kullanicinin yas/cinsiyet/renk/tarz secimleri dogal dilde bir
profil metnine donusturulur, bu metin Gemini'nin embedding
modeline gonderilir ve donen vektor, urunlerin ONCEDEN
CIKARILMIS embeddingleriyle (pgvector cosine distance) anlamsal
olarak karsilastirilir.

Baska bir LLM entegrasyonu icat edilmedi: generate_embedding,
semantic search'te (crud.semantic_search_products) zaten
kullanilan AYNI Gemini baglantisidir. Eslestirme sorgusu da
crud.semantic_search_products'in kendisidir — bu modul sadece
"kullanici secimleri -> anlamli bir prompt" donusumunu yapar.
"""

from app.embeddings import generate_embedding


def build_style_profile_prompt(
    age: int | None,
    gender: str | None,
    colors: list[str] | None,
    styles: list[str] | None,
) -> str:
    """
    Kullanicinin secimlerini zengin bir dogal dil profiline
    cevirir. Bu metin dogrudan embedding modeline gider; yapisal
    bir filtre DEGILDIR — model bunu kelime eslestirmesi degil
    ANLAM olarak isler ("pastel tonlar seven, rahat ama şık
    parcalar arayan 24 yasinda bir kadin" gibi).
    """

    colors = [c.strip() for c in (colors or []) if c and c.strip()]
    styles = [s.strip() for s in (styles or []) if s and s.strip()]

    intro_parts = []

    if age:
        intro_parts.append(f"{age} yaşında")

    gender_normalized = (gender or "").strip().lower()

    if gender_normalized in ("kadın", "kadin", "women", "woman", "female"):
        intro_parts.append("bir kadın")
    elif gender_normalized in ("erkek", "men", "man", "male"):
        intro_parts.append("bir erkek")
    elif gender_normalized:
        intro_parts.append("bir alışverişçi")

    intro = " ".join(intro_parts) if intro_parts else "Bir alışverişçi"

    sentences = [f"{intro} için kişisel giyim tarzı profili."]

    if colors:
        sentences.append(
            "En çok sevdiği renkler: "
            + ", ".join(colors)
            + ". Gardırobunda bu renk tonlarının baskın "
            "olmasını istiyor."
        )

    if styles:
        sentences.append(
            "Beğendiği kombin ve tarz yönelimleri: "
            + ", ".join(styles)
            + ". Bu tarzların ruhuna uygun kesim ve parçalar "
            "arıyor."
        )

    sentences.append(
        "Ona bu profile en uygun, günlük hayatında giyebileceği "
        "moda ürünlerini öner."
    )

    return " ".join(sentences)


def embed_style_profile(prompt: str) -> list[float]:
    """
    Profil metnini Gemini embedding modeline gonderir.

    Semantic search'teki generate_embedding ile AYNI fonksiyon;
    burada ayri bir LLM baglantisi kurulmuyor.
    """

    return generate_embedding(prompt)


def resolve_gender_filter(gender: str | None) -> str | None:
    """
    Serbest metin cinsiyet girdisini crud.semantic_search_products'in
    bildigi "men"/"women" degerine cevirir. Eslesmezse None doner
    (filtre uygulanmaz) — kisitlayici bir varsayilan degil.
    """

    normalized = (gender or "").strip().lower()

    if normalized in ("kadın", "kadin", "women", "woman", "female"):
        return "women"

    if normalized in ("erkek", "men", "man", "male"):
        return "men"

    return None
