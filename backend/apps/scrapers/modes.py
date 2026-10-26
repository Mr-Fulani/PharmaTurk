"""Три режима запуска парсеров — подсказки для админки и документации.

1. Один товар — ссылка на карточку товара.
2. Вся категория — ссылка на страницу категории; все страницы проходятся
   цепочкой чанков до конца (или до «Макс. товаров»).
3. Весь сайт — тип задачи «Весь сайт»: парсер сам находит категории
   (parse_categories) и обходит их по очереди. У Instagram третий режим —
   весь профиль (задача Instagram с username).

У IlacFiyati есть ещё тип «Только изменения» (docs/PARSER_MODES.md): листинги
по строкам и sitemap, карточка открывается только при отличии строки.
"""

PARSER_MODES = {
    "ilacfiyati": {
        "label": "IlacFiyati",
        "product": "https://ilacfiyati.com/ilaclar/majezik-100-mg-15-film-tablet",
        "category": "https://ilacfiyati.com/takviye-edici-gida/bagisiklik-destek-urunleri",
        "site": "лекарства (/ilaclar) и БАДы (/takviye-edici-gida) целиком",
        "note": (
            "Регулярное обновление — тип «Только изменения»: открываются только новые "
            "карточки и те, чья строка в листинге изменилась; «Весь сайт» — раз в месяц."
        ),
    },
    "zara": {
        "label": "Zara",
        "product": "https://www.zara.com/tr/tr/<название>-p02286602.html",
        "category": "https://www.zara.com/tr/tr/kadin-elbiseler-l1066.html",
        "site": "все разделы меню магазина (~340, с промо-подборками — обход долгий)",
    },
    "bershka": {
        "label": "Bershka",
        "product": "https://www.bershka.com/tr/<название>-c0p228309045.html",
        "category": "https://www.bershka.com/tr/kadin/giyim/elbise-n3802.html?celement=1010193213",
        "site": "дерево категорий магазина (API)",
        "note": "Ссылку категории вставлять целиком, вместе с ?celement=…",
    },
    "pullandbear": {
        "label": "Pull&Bear",
        "product": "https://www.pullandbear.com/tr/<название>-l03233901?pelement=752040619",
        "category": "https://www.pullandbear.com/tr/kadin/giyim/pantolonlar/kargo-n6603.html?celement=1030475974",
        "site": "дерево категорий магазина (API)",
        "note": "Ссылку категории вставлять целиком, вместе с ?celement=…",
    },
    "massimodutti": {
        "label": "Massimo Dutti",
        "product": "https://www.massimodutti.com/tr/<название>-l00648198?pelement=61733884",
        "category": "ссылка на страницу раздела (…-n<номер>, лучше с ?celement=…)",
        "site": "дерево категорий магазина (API)",
    },
    "lcw": {
        "label": "LC Waikiki",
        "product": "https://www.lcw.com/<название>-o-5271243",
        "category": "https://www.lcw.com/erkek-tisort-t-345",
        "site": "подразделы 12 корней каталога (Kadın, Erkek, Çocuk, Bebek, Ev & Yaşam…)",
    },
    "flo": {
        "label": "FLO",
        "product": "https://www.flo.com.tr/urun/<название>-101987837",
        "category": "https://www.flo.com.tr/sandalet",
        "site": "дерево категорий /tum-kategoriler (~130 разделов)",
        "note": "Идёт через платный прокси — большие прогоны только с согласия.",
    },
    "ikea": {
        "label": "IKEA",
        "product": "https://www.ikea.com.tr/urun/<название>-80541594",
        "category": "https://www.ikea.com.tr/kategori/kanepeler",
        "site": "разделы меню «Ürünler» (~22)",
    },
    "ummaland": {
        "label": "UmmaLand",
        "product": "https://umma-land.com/product/bolshaya-kniga-ramadana",
        "category": "https://umma-land.com/product-category/books",
        "site": "все категории магазина",
    },
    "instagram": {
        "label": "Instagram",
        "product": "https://www.instagram.com/p/<код поста>/",
        "category": "—",
        "site": "весь профиль: «Задачи Instagram» → username и «Максимум постов» (например, 5000)",
        "note": "Нужен вход: cookie sessionid в настройках парсера Instagram.",
    },
}
