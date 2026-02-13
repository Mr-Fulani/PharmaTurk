"""Добавляет популярные бренды парфюмерии с primary_category_slug=perfumery."""

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.db import transaction

from apps.catalog.models import Brand


class Command(BaseCommand):
    help = "Добавляет популярные бренды парфюмерии (international + Turkish + Arabic)"

    # Популярные бренды парфюмерии (международные, турецкие, арабские)
    PERFUMERY_BRANDS = [
        # Люкс
        ("Chanel", "Французский дом моды и парфюмерии. Chanel №5, Coco Mademoiselle.", "https://www.chanel.com"),
        ("Dior", "Французский luxury-бренд. Sauvage, Miss Dior, J'adore.", "https://www.dior.com"),
        ("Gucci", "Итальянский модный дом. Gucci Bloom, Flora, Guilty.", "https://www.gucci.com"),
        ("Versace", "Итальянский luxury-бренд. Versace Pour Homme, Bright Crystal.", "https://www.versace.com"),
        ("Armani", "Giorgio Armani — итальянская парфюмерия. Acqua di Gio, Si.", "https://www.giorgioarmani.com"),
        ("Dolce & Gabbana", "Итальянский дом. Light Blue, The One, Intenso.", "https://www.dolcegabbana.com"),
        ("Yves Saint Laurent", "YSL — французская парфюмерия. Black Opium, Libre, Mon Paris.", "https://www.ysl.com"),
        ("Tom Ford", "Люксовая парфюмерия. Black Orchid, Oud Wood, Lost Cherry.", "https://www.tomford.com"),
        ("Givenchy", "Французский дом. Gentlemen, L'Interdit, Irresistible.", "https://www.givenchy.com"),
        ("Prada", "Итальянская парфюмерия. Luna Rossa, Paradoxe, Candy.", "https://www.prada.com"),
        ("Bulgari", "Итальянский ювелирный и парфюмерный дом. Omnia, Man in Black.", "https://www.bulgari.com"),
        ("Valentino", "Итальянская парфюмерия. Born in Roma, Voce Viva.", "https://www.valentino.com"),
        ("Boss", "Hugo Boss — немецкая парфюмерия. Bottled, The Scent.", "https://www.hugoboss.com"),
        ("Lancôme", "Французская косметика и парфюмерия. La Vie Est Belle, Idôle.", "https://www.lancome.com"),
        ("Estée Lauder", "Американская luxury-косметика. Beautiful, Pleasures, Modern Muse.", "https://www.esteelauder.com"),
        # Premium
        ("Paco Rabanne", "Испанский дизайнер. 1 Million, Invictus, Fame.", "https://www.pacorabanne.com"),
        ("Calvin Klein", "Американский бренд. CK One, Eternity, Obsession.", "https://www.calvinklein.com"),
        ("Jean Paul Gaultier", "Французский дизайнер. Le Male, La Belle, Scandal.", "https://www.jeanpaulgaultier.com"),
        ("Carolina Herrera", "Венесуэльский дизайнер. Good Girl, 212, CH.", "https://www.carolinaherrera.com"),
        ("Montblanc", "Немецкая парфюмерия. Legend, Explorer, Emblem.", "https://www.montblanc.com"),
        ("Azzaro", "Французская парфюмерия. Azzaro Pour Homme, Most Wanted.", "https://www.azzaro.com"),
        ("Diesel", "Итальянский бренд. Only The Brave, Fuel for Life.", "https://www.diesel.com"),
        ("Kenzo", "Японско-французский бренд. Flower, L'Eau par Kenzo.", "https://www.kenzo.com"),
        ("Issey Miyake", "Японский дизайнер. L'Eau d'Issey, Nuit d'Issey.", "https://www.isseymiyake.com"),
        ("Davidoff", "Швейцарский бренд. Cool Water, The One.", "https://www.davidoff.com"),
        ("Guess", "Американский бренд. Seductive, 1981.", "https://www.guess.com"),
        ("Giorgio Beverly Hills", "Классическая парфюмерия. Giorgio.", "https://www.giorgiobeverlyhills.com"),
        # Турецкие бренды парфюмерии
        ("Atelier Rebul", "Турецкая нишевая парфюмерия. Роза, жасмин, oud.", "https://www.atelierrebul.com"),
        ("Nishane", "Турецкая luxury-парфюмерия из Стамбула.", "https://www.nishane.com"),
        ("Memo Paris", "Турецкий бренд ароматов. Восточные мотивы.", ""),
        ("Arifoglu", "Турецкая парфюмерия и косметика.", ""),
        ("Flormar", "Турецкая косметика и парфюмерия. Доступные цены.", "https://www.flormar.com.tr"),
        ("Golden Rose", "Турецкая косметика. Парфюмерная вода.", "https://www.goldenrose.com.tr"),
        ("Pera Palace", "Турецкий бренд ароматов. Восточные композиции.", ""),
        # Арабские бренды парфюмерии
        ("Ajmal", "Арабская парфюмерия с 1951. Oud, мускус, восточные ароматы. 300+ магазинов.", "https://www.ajmalperfume.com"),
        ("Rasasi", "Один из крупнейших арабских брендов. Oud, традиционные и современные ароматы.", "https://www.rasasi.com"),
        ("Swiss Arabian", "Первый производитель парфюмерии в ОАЭ. Oud, амбра, шафран, роза.", "https://www.swissarabian.com"),
        ("Amouage", "Люксовая оманская парфюмерия. Восточные композиции, oud.", "https://www.amouage.com"),
        ("Al Haramain", "Арабская парфюмерия. Oud, амбра, мускус.", "https://www.alharamainperfumes.com"),
        ("Lattafa", "Популярная арабская парфюмерия. Oud, восточные ароматы по доступным ценам.", "https://www.lattafa.com"),
        ("Afnan", "Арабская парфюмерия. Oud, амбра, мускус.", "https://www.afnanperfumes.com"),
        ("Armaf", "Арабская парфюмерия из ОАЭ. Oud, восточные ароматы.", "https://www.armafperfumes.com"),
        ("Nabeel", "Арабская парфюмерия. Oud, амбра, мускус.", "https://www.nabeelperfumes.com"),
        ("Surrati", "Традиционная арабская парфюмерия. Oud, восточные композиции.", ""),
        ("Oriental Oud", "Арабская парфюмерия. Oud, амбра, мускус.", ""),
        ("Paris Corner", "Арабская парфюмерия. Oud, восточные ароматы.", ""),
    ]

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Добавляем популярные бренды парфюмерии..."))
        created = 0
        updated = 0
        seen_slugs = set()

        with transaction.atomic():
            for name, description, website in self.PERFUMERY_BRANDS:
                slug = slugify(name)
                if not slug or slug in seen_slugs:
                    continue
                seen_slugs.add(slug)

                brand, was_created = Brand.objects.update_or_create(
                    slug=slug,
                    defaults={
                        "name": name,
                        "description": description,
                        "website": website or "",
                        "is_active": True,
                        "primary_category_slug": "perfumery",
                    },
                )
                if was_created:
                    created += 1
                    self.stdout.write(f"  ✓ Создан: {name}")
                else:
                    if brand.primary_category_slug != "perfumery":
                        brand.primary_category_slug = "perfumery"
                        brand.save()
                        updated += 1
                        self.stdout.write(f"  ↻ Обновлён: {name} (primary_category_slug=perfumery)")

        self.stdout.write(self.style.SUCCESS(f"Готово: создано {created}, обновлено {updated} брендов парфюмерии."))
