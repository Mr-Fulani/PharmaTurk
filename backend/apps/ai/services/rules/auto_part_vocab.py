"""Словарь автозапчастей: вид детали, подписи характеристик, написание марок.

Ключ вида — адрес раздела магазина-источника (``fren-balatasi``): он же получается из
турецкого названия («Fren Balatası») сворачиванием в латиницу. Значение — (русское
название в единственном числе, английское). Первый источник — Aloparça: все его
подразделы на 24.11.2026 (``sitemaps/categories.xml``) плюс виды третьего уровня,
встреченные в карточках. Вида нет в словаре — карточка не собирается (ошибка обработки
с названием вида), а не получает выдуманное название.
"""

from __future__ import annotations

import re

from django.utils.text import slugify

from apps.catalog.utils.tr_vocab import normalize_ascii_text

PART_KINDS: dict[str, tuple[str, str]] = {
    # --- зажигание ---
    "atesleme-bobini": ("катушка зажигания", "Ignition Coil"),
    "atesleme-bujisi": ("свеча зажигания", "Spark Plug"),
    "buji-kablosu": ("провода зажигания", "Ignition Cable Set"),
    "distributor": ("распределитель зажигания", "Ignition Distributor"),
    "distributor-parcalari": ("детали распределителя зажигания", "Distributor Parts"),
    "isitma-bujisi": ("свеча накаливания", "Glow Plug"),
    "kizdirma-bujisi": ("свеча накаливания", "Glow Plug"),
    "kizdirma-role": ("реле свечей накаливания", "Glow Plug Relay"),
    # --- освещение и зеркала ---
    "ampul": ("автомобильная лампа", "Bulb"),
    "ayna-cami": ("зеркальный элемент", "Mirror Glass"),
    "camurluk-sinyali": ("боковой указатель поворота", "Side Indicator"),
    "dikiz-ayna-sinyali": ("указатель поворота в зеркале", "Mirror Indicator"),
    "dikiz-aynasi": ("наружное зеркало", "Wing Mirror"),
    "ek-fren-lambasi-3-stop": ("дополнительный стоп-сигнал", "Third Brake Light"),
    "far": ("фара", "Headlight"),
    "far-ayar-motoru": ("корректор фар", "Headlight Levelling Motor"),
    "far-beyni": ("блок управления фарой", "Headlight Control Unit"),
    "geri-vites-lambasi": ("фонарь заднего хода", "Reversing Light"),
    "gunduz-fari": ("дневной ходовой огонь", "Daytime Running Light"),
    "plaka-lambasi": ("фонарь подсветки номера", "Licence Plate Light"),
    "sinyal-lambasi": ("указатель поворота", "Indicator Light"),
    "sis-fari": ("противотуманная фара", "Fog Light"),
    "stop-lambasi": ("задний фонарь", "Tail Light"),
    # --- сцепление ---
    "debriyaj-catali": ("вилка сцепления", "Clutch Fork"),
    "debriyaj-merkezi-ve-rulmani": ("цилиндр и выжимной подшипник сцепления", "Clutch Cylinder and Release Bearing"),
    "debriyaj-musuru": ("датчик педали сцепления", "Clutch Pedal Switch"),
    "debriyaj-pedali": ("педаль сцепления", "Clutch Pedal"),
    "debriyaj-seti": ("комплект сцепления", "Clutch Kit"),
    "debriyaj-teli": ("трос сцепления", "Clutch Cable"),
    "sanziman-yag": ("трансмиссионное масло", "Gearbox Oil"),
    "volan": ("маховик", "Flywheel"),
    "volan-civata-ve-rulman": ("болты и подшипник маховика", "Flywheel Bolts and Bearing"),
    # --- рулевое ---
    "airbag-sargisi-zemberek": ("шлейф подушки безопасности", "Airbag Clock Spring"),
    "direksiyon-hidrolik-yag-deposu": ("бачок гидроусилителя руля", "Power Steering Reservoir"),
    "direksiyon-hortumu": ("шланг гидроусилителя руля", "Power Steering Hose"),
    "direksiyon-korugu": ("пыльник рулевой рейки", "Steering Rack Boot"),
    "direksiyon-kutusu": ("рулевая рейка", "Steering Rack"),
    "direksiyon-pompasi": ("насос гидроусилителя руля", "Power Steering Pump"),
    "direksiyon-yag": ("жидкость гидроусилителя руля", "Power Steering Fluid"),
    "far-sinyal-ve-silecek-kolu": ("подрулевой переключатель", "Steering Column Switch"),
    # --- кузов снаружи ---
    "ayna-kapagi": ("крышка зеркала", "Mirror Cover"),
    "bagaj-amortisoru": ("амортизатор багажника", "Boot Gas Strut"),
    "cam-krikosu": ("стеклоподъёмник", "Window Regulator"),
    "cam-su-deposu": ("бачок омывателя", "Washer Fluid Reservoir"),
    "kapi-kilidi": ("замок двери", "Door Lock"),
    "kaput-teli": ("трос капота", "Bonnet Cable"),
    "motor-alt-muhafaza": ("защита двигателя", "Engine Undertray"),
    "motor-kaput-amortisoru": ("амортизатор капота", "Bonnet Gas Strut"),
    "motor-kaput-kilidi": ("замок капота", "Bonnet Lock"),
    "silecek-mekanizmasi": ("трапеция стеклоочистителя", "Wiper Linkage"),
    "silecek-motoru": ("мотор стеклоочистителя", "Wiper Motor"),
    "silecek-supurgesi": ("щётка стеклоочистителя", "Wiper Blade"),
    "surgulu-kapi-makarasi": ("ролик сдвижной двери", "Sliding Door Roller"),
    "tavan-anteni": ("антенна на крышу", "Roof Antenna"),
    # --- электрика ---
    "alternator": ("генератор", "Alternator"),
    "alternator-kasnagi": ("шкив генератора", "Alternator Pulley"),
    "alternator-parcalari": ("детали генератора", "Alternator Parts"),
    "ayna-kumanda-dugmesi": ("переключатель регулировки зеркал", "Mirror Adjustment Switch"),
    "cam-acma-dugmesi": ("кнопка стеклоподъёмника", "Window Switch"),
    "cam-su-motoru": ("насос омывателя", "Washer Pump"),
    "dis-hava-sicaklik-sensoru": ("датчик наружной температуры", "Outside Temperature Sensor"),
    "dortlu-flasor-dugmesi": ("кнопка аварийной сигнализации", "Hazard Light Switch"),
    "far-anahtari": ("переключатель света фар", "Headlight Switch"),
    "far-kumanda-kolu": ("подрулевой переключатель света", "Headlight Stalk Switch"),
    "korna": ("звуковой сигнал", "Horn"),
    "mars-dinamo-parcalari": ("детали стартера", "Starter Parts"),
    "mars-dinamosu": ("стартер", "Starter Motor"),
    "park-sensoru": ("датчик парковки", "Parking Sensor"),
    "role-ve-flasor": ("реле", "Relay"),
    "sigorta": ("предохранитель", "Fuse"),
    "silecek-kumanda-kolu": ("подрулевой переключатель стеклоочистителя", "Wiper Stalk Switch"),
    "sinyal-kumanda-kolu": ("подрулевой переключатель поворотов", "Indicator Stalk Switch"),
    # --- фильтры ---
    "hava-filtresi": ("воздушный фильтр", "Air Filter"),
    "karter-tapasi": ("пробка поддона картера", "Sump Plug"),
    "polen-filtresi": ("салонный фильтр", "Cabin Filter"),
    "sanziman-yag-filtresi": ("фильтр коробки передач", "Transmission Filter"),
    "yag-filtresi": ("масляный фильтр", "Oil Filter"),
    "yakit-filtresi": ("топливный фильтр", "Fuel Filter"),
    # --- тормоза ---
    "abs-sensoru": ("датчик ABS", "ABS Sensor"),
    "balata-ikaz-kablosu": ("датчик износа тормозных колодок", "Brake Pad Wear Sensor"),
    "el-fren-balatasi": ("колодки стояночного тормоза", "Handbrake Shoes"),
    "el-fren-kolu": ("рычаг стояночного тормоза", "Handbrake Lever"),
    "el-fren-teli": ("трос стояночного тормоза", "Handbrake Cable"),
    "fren-ana-merkez": ("главный тормозной цилиндр", "Brake Master Cylinder"),
    "fren-balatasi": ("тормозные колодки", "Brake Pads"),
    "fren-disk-balata": ("тормозные колодки дисковые", "Disc Brake Pads"),
    "fren-disk": ("тормозной диск", "Brake Disc"),
    "fren-disk-ayna": ("тормозной диск", "Brake Disc"),
    "fren-hidrolik-yag": ("тормозная жидкость", "Brake Fluid"),
    "fren-hortumu": ("тормозной шланг", "Brake Hose"),
    "fren-kaliper": ("тормозной суппорт", "Brake Caliper"),
    "fren-limitor": ("регулятор тормозных сил", "Brake Force Regulator"),
    "fren-musuru": ("датчик стоп-сигнала", "Brake Light Switch"),
    "fren-pabuclu-balata": ("барабанные тормозные колодки", "Brake Shoes"),
    "fren-silindiri": ("рабочий тормозной цилиндр", "Wheel Brake Cylinder"),
    "fren-vakum-pompa": ("вакуумный насос тормозов", "Brake Vacuum Pump"),
    "geri-vites-musuru": ("датчик заднего хода", "Reverse Light Switch"),
    "kampana": ("тормозной барабан", "Brake Drum"),
    "lastik-basinc-sensoru": ("датчик давления в шинах", "Tyre Pressure Sensor"),
    "westinghouse": ("вакуумный усилитель тормозов", "Brake Servo"),
    "westinghouse-hortumu": ("шланг вакуумного усилителя тормозов", "Brake Servo Hose"),
    # --- двигатель ---
    "ana-yatak": ("коренные вкладыши", "Main Bearings"),
    "ay-yatak": ("упорные полукольца коленвала", "Crankshaft Thrust Washers"),
    "cesitli-conta": ("прокладка", "Gasket"),
    "conta-ve-kece": ("прокладки и сальники", "Gaskets and Seals"),
    "eksantrik-devir-sensoru": ("датчик положения распредвала", "Camshaft Position Sensor"),
    "eksantrik-kapak-contasi": ("прокладка крышки распредвала", "Camshaft Cover Gasket"),
    "eksantrik-kecesi": ("сальник распредвала", "Camshaft Seal"),
    "eksantrik-konum-valfi": ("клапан фазорегулятора", "Camshaft Adjuster Valve"),
    "eksantrik-mili": ("распределительный вал", "Camshaft"),
    "eksantrik-vanos-disli": ("шестерня фазорегулятора", "Camshaft Adjuster"),
    "elektrik-ve-sensor": ("датчик двигателя", "Engine Sensor"),
    "gomlek": ("гильза цилиндра", "Cylinder Liner"),
    "hava-debimetresi": ("расходомер воздуха", "Mass Air Flow Sensor"),
    "hava-hortumu": ("воздушный патрубок", "Air Intake Hose"),
    "karter-contasi": ("прокладка поддона картера", "Sump Gasket"),
    "kol-burcu": ("втулка шатуна", "Connecting Rod Bush"),
    "kol-yatak": ("шатунные вкладыши", "Connecting Rod Bearings"),
    "komple-motor": ("двигатель в сборе", "Complete Engine"),
    "krank": ("коленчатый вал", "Crankshaft"),
    "krank-disli": ("шестерня коленвала", "Crankshaft Gear"),
    "krank-kasnak": ("шкив коленвала", "Crankshaft Pulley"),
    "krank-kecesi": ("сальник коленвала", "Crankshaft Seal"),
    "krank-sensoru": ("датчик положения коленвала", "Crankshaft Position Sensor"),
    "manifold": ("коллектор", "Manifold"),
    "manifolt-conta": ("прокладка коллектора", "Manifold Gasket"),
    "map-sensoru": ("датчик абсолютного давления", "MAP Sensor"),
    "mazot-stop-musuru": ("клапан отсечки топлива", "Fuel Shut-Off Valve"),
    "motor-rektefiye": ("детали для ремонта двигателя", "Engine Overhaul Parts"),
    "motor-su-tapasi": ("заглушка блока цилиндров", "Core Plug"),
    "motor-takozu": ("опора двигателя", "Engine Mount"),
    "motor-ust-kapagi-kulbutor": ("клапанная крышка", "Rocker Cover"),
    "motor-yag-karteri": ("поддон картера", "Oil Sump"),
    "motor-yag-sogutucu": ("масляный радиатор", "Engine Oil Cooler"),
    "nox-sensoru": ("датчик NOx", "NOx Sensor"),
    "oksijen-lambda-sensoru": ("лямбда-зонд", "Lambda Sensor"),
    "piston-kolu": ("шатун", "Connecting Rod"),
    "piston-segman": ("поршень с кольцами", "Piston with Rings"),
    "segman": ("поршневые кольца", "Piston Rings"),
    "silindir-kapagi": ("головка блока цилиндров", "Cylinder Head"),
    "silindir-kapak-contasi": ("прокладка головки блока цилиндров", "Cylinder Head Gasket"),
    "silindir-kapak-saplamasi": ("болты головки блока цилиндров", "Cylinder Head Bolts"),
    "supap": ("клапан", "Valve"),
    "supap-gayd-ve-baga": ("направляющая и седло клапана", "Valve Guide and Seat"),
    "supap-lastigi": ("маслосъёмный колпачок", "Valve Stem Seal"),
    "supap-tapet-itici-fincan": ("толкатель клапана", "Valve Tappet"),
    "supap-tusu": ("коромысло клапана", "Rocker Arm"),
    "takim-conta": ("комплект прокладок двигателя", "Engine Gasket Set"),
    "turbo-hortum-ve-conta": ("патрубок турбины", "Turbo Hose"),
    "turbo-sarj": ("турбокомпрессор", "Turbocharger"),
    "turbo-valfi-elektrovana": ("клапан управления турбиной", "Boost Control Valve"),
    "ust-kapak-contasi-kulbutor": ("прокладка клапанной крышки", "Rocker Cover Gasket"),
    "vuruntu-sensoru": ("датчик детонации", "Knock Sensor"),
    "yag-filtre-kutugu": ("корпус масляного фильтра", "Oil Filter Housing"),
    "yag-musuru": ("датчик давления масла", "Oil Pressure Switch"),
    "yag-pompa-contasi": ("прокладка масляного насоса", "Oil Pump Gasket"),
    "yag-pompasi": ("масляный насос", "Oil Pump"),
    "yag-seperatoru": ("маслоотделитель", "Oil Separator"),
    "yag-seviye-sensor-ve-cubugu": ("датчик уровня масла", "Oil Level Sensor"),
    "yaglama-jeti": ("масляная форсунка", "Oil Jet"),
    # --- решётки и панели ---
    "far-alt-citasi": ("молдинг под фару", "Headlight Lower Trim"),
    "far-alt-panjuru": ("решётка под фару", "Headlight Lower Grille"),
    "far-baglanti-saci": ("панель крепления фары", "Headlight Mounting Panel"),
    "far-bakaliti": ("кронштейн фары", "Headlight Bracket"),
    "far-braketi": ("кронштейн фары", "Headlight Bracket"),
    "far-cercevesi": ("рамка фары", "Headlight Frame"),
    "far-kasi": ("накладка фары", "Headlight Eyelid"),
    "far-kusagi": ("накладка под фару", "Headlight Trim Strip"),
    "far-saci": ("панель фары", "Headlight Panel"),
    "far-yuva-saci": ("панель гнезда фары", "Headlight Housing Panel"),
    "far-yuvasi": ("корпус фары", "Headlight Housing"),
    "gunduz-far-panjuru": ("решётка дневного ходового огня", "Daytime Running Light Grille"),
    "gunduz-far-yuvasi": ("корпус дневного ходового огня", "Daytime Running Light Housing"),
    "havalandirma-izgarasi": ("вентиляционная решётка", "Ventilation Grille"),
    "panel": ("передняя панель", "Front Panel"),
    "panel-braketi": ("кронштейн передней панели", "Front Panel Bracket"),
    "panel-kapagi": ("крышка передней панели", "Front Panel Cover"),
    "panel-takviyesi": ("усилитель передней панели", "Front Panel Reinforcement"),
    "panel-tasiyici": ("несущая передней панели", "Front Panel Carrier"),
    "panel-traversi": ("поперечина передней панели", "Front Panel Crossmember"),
    "panjur": ("решётка радиатора", "Radiator Grille"),
    "panjur-braketi": ("кронштейн решётки радиатора", "Grille Bracket"),
    "panjur-cercevesi": ("рамка решётки радиатора", "Grille Frame"),
    "panjur-citasi": ("молдинг решётки радиатора", "Grille Trim"),
    "panjur-kusagi": ("накладка решётки радиатора", "Grille Strip"),
    "panjur-paneli": ("панель решётки радиатора", "Grille Panel"),
    "panjur-saci": ("панель решётки радиатора", "Grille Panel"),
    "panjur-takviyesi": ("усилитель решётки радиатора", "Grille Reinforcement"),
    "stop-lamba-yuvasi": ("корпус заднего фонаря", "Tail Light Housing"),
    # --- коробка передач ---
    "kece": ("сальник коробки передач", "Gearbox Seal"),
    "kilometre-hiz-sensoru": ("датчик скорости", "Speed Sensor"),
    "rulman-tamir-takimi": ("ремкомплект подшипников коробки передач", "Gearbox Bearing Kit"),
    "saft-kardan-mili": ("карданный вал", "Propshaft"),
    "saft-takozu": ("опора карданного вала", "Propshaft Mount"),
    "sanziman-karti": ("блок управления коробкой передач", "Transmission Control Unit"),
    "sanziman-motoru": ("актуатор коробки передач", "Gearbox Actuator"),
    "sanziman-takozu": ("опора коробки передач", "Gearbox Mount"),
    "sanziman-yag-karteri": ("поддон коробки передач", "Transmission Oil Pan"),
    "sanziman-yag-sogutucu": ("радиатор масла коробки передач", "Transmission Oil Cooler"),
    "vites-teli": ("трос переключения передач", "Gear Shift Cable"),
    # --- охлаждение, отопление, кондиционер ---
    "devirdaim-hortumu": ("патрубок водяного насоса", "Water Pump Hose"),
    "devirdaim-su-pompasi": ("водяной насос", "Water Pump"),
    "egzoz-sicaklik-sensoru": ("датчик температуры выхлопных газов", "Exhaust Gas Temperature Sensor"),
    "evaporator": ("испаритель кондиционера", "Air Conditioning Evaporator"),
    "fan-musuru": ("датчик включения вентилятора", "Radiator Fan Switch"),
    "hararet-musuru": ("датчик температуры охлаждающей жидкости", "Coolant Temperature Sensor"),
    "kalorifer-hortumu": ("патрубок отопителя", "Heater Hose"),
    "kalorifer-motoru": ("мотор отопителя", "Heater Blower Motor"),
    "kalorifer-muslugu": ("кран отопителя", "Heater Valve"),
    "kalorifer-radyatoru": ("радиатор отопителя", "Heater Core"),
    "klima-basinc-musuru": ("датчик давления кондиционера", "Air Conditioning Pressure Switch"),
    "klima-hortumu": ("шланг кондиционера", "Air Conditioning Hose"),
    "klima-kompresoru": ("компрессор кондиционера", "Air Conditioning Compressor"),
    "klima-kurutucu-tup": ("осушитель кондиционера", "Air Conditioning Dryer"),
    "klima-radyatoru": ("радиатор кондиционера", "Air Conditioning Condenser"),
    "radyator-fan-ve-motoru": ("вентилятор радиатора", "Radiator Fan"),
    "radyator-hortumu": ("патрубок радиатора", "Radiator Hose"),
    "radyator-kapagi": ("крышка радиатора", "Radiator Cap"),
    "radyator-yedek-su-depo-kapagi": ("крышка расширительного бачка", "Expansion Tank Cap"),
    "radyator-yedek-su-deposu": ("расширительный бачок", "Expansion Tank"),
    "rezistansi": ("резистор вентилятора отопителя", "Blower Motor Resistor"),
    "sogutma-fani-fan-termik": ("вискомуфта вентилятора", "Fan Clutch"),
    "su-flans": ("фланец охлаждающей жидкости", "Coolant Flange"),
    "su-radyatoru": ("радиатор охлаждения", "Radiator"),
    "termostat": ("термостат", "Thermostat"),
    "termostat-govdesi": ("корпус термостата", "Thermostat Housing"),
    "turbo-radyatoru": ("интеркулер", "Intercooler"),
    "valf": ("клапан системы охлаждения", "Coolant Valve"),
    # --- подвеска и привод ---
    "aks-kafasi": ("шарнир равных угловых скоростей", "CV Joint"),
    "aks-kecesi": ("сальник привода", "Driveshaft Seal"),
    "aks-komple": ("приводной вал в сборе", "Driveshaft"),
    "aks-korugu": ("пыльник шарнира привода", "CV Boot"),
    "aks-tasiyici": ("поворотный кулак", "Steering Knuckle"),
    "amortisor": ("амортизатор", "Shock Absorber"),
    "amortisor-korugu-ve-darbe-emici": ("пыльник и отбойник амортизатора", "Shock Absorber Boot and Bump Stop"),
    "amortisor-rulmani": ("опорный подшипник амортизатора", "Strut Bearing"),
    "amortisor-tabla-takozu": ("опора амортизатора", "Strut Mount"),
    "amortisor-takozu-ve-rulmani": ("опора амортизатора с подшипником", "Strut Mount with Bearing"),
    "denge-kolu": ("реактивная тяга", "Trailing Arm"),
    "helezon-get-lastigi": ("проставка пружины", "Spring Seat"),
    "helezon-yayi": ("пружина подвески", "Coil Spring"),
    "porya": ("ступица колеса", "Wheel Hub"),
    "porya-ve-rulman": ("ступичный подшипник", "Wheel Bearing"),
    "porya-rulmani": ("ступичный подшипник", "Wheel Bearing"),
    "rot-basi": ("рулевой наконечник", "Tie Rod End"),
    "rot-mili": ("рулевая тяга", "Tie Rod"),
    "rotil": ("шаровая опора", "Ball Joint"),
    "salincak": ("рычаг подвески", "Control Arm"),
    "salincak-burcu": ("сайлентблок рычага", "Control Arm Bush"),
    "travers-torsiyon-takoz-burc": ("сайлентблок подрамника", "Subframe Bush"),
    "viraj-demir-aski-rotu": ("стойка стабилизатора", "Stabiliser Link"),
    "viraj-demir-lastigi": ("втулка стабилизатора", "Stabiliser Bush"),
    "viraj-demiri": ("стабилизатор поперечной устойчивости", "Anti-Roll Bar"),
    # --- бампер ---
    "darbe-emici": ("абсорбер бампера", "Bumper Absorber"),
    "plaka-kusagi": ("накладка под номерной знак", "Licence Plate Trim"),
    "plakalik": ("рамка номерного знака", "Licence Plate Holder"),
    "sinyal-cercevesi": ("рамка указателя поворота", "Indicator Frame"),
    "sis-far-braketi": ("кронштейн противотуманной фары", "Fog Light Bracket"),
    "sis-far-kusagi": ("накладка противотуманной фары", "Fog Light Trim Strip"),
    "sis-far-yuvasi": ("корпус противотуманной фары", "Fog Light Housing"),
    "sis-fari-cercevesi": ("рамка противотуманной фары", "Fog Light Frame"),
    "sis-kapak-citasi": ("молдинг заглушки противотуманной фары", "Fog Light Cover Trim"),
    "takviye-braketi": ("кронштейн усилителя бампера", "Bumper Reinforcement Bracket"),
    "tampon": ("бампер", "Bumper"),
    "tampon-alt-muhafaza": ("нижняя защита бампера", "Bumper Undertray"),
    "tampon-alt-parca": ("нижняя часть бампера", "Bumper Lower Section"),
    "tampon-bakaliti": ("кронштейн бампера", "Bumper Bracket"),
    "tampon-bandi": ("молдинг бампера", "Bumper Moulding"),
    "tampon-basamagi": ("подножка бампера", "Bumper Step"),
    "tampon-braketi": ("кронштейн бампера", "Bumper Bracket"),
    "tampon-ceki-demir-kapagi": ("заглушка буксировочной проушины", "Tow Hook Cover"),
    "tampon-citasi": ("молдинг бампера", "Bumper Trim"),
    "tampon-demiri": ("усилитель бампера", "Bumper Reinforcement Bar"),
    "tampon-far-yikama-kapagi": ("крышка омывателя фар", "Headlight Washer Cover"),
    "tampon-hava-yonlendirici": ("воздуховод бампера", "Bumper Air Duct"),
    "tampon-kaplamasi": ("накладка бампера", "Bumper Cover"),
    "tampon-korumasi": ("защита бампера", "Bumper Guard"),
    "tampon-kosesi": ("угол бампера", "Bumper Corner"),
    "tampon-kusagi": ("накладка бампера", "Bumper Strip"),
    "tampon-nikelaji": ("хромированная накладка бампера", "Bumper Chrome Trim"),
    "tampon-panjur-cercevesi": ("рамка решётки бампера", "Bumper Grille Frame"),
    "tampon-panjur-citasi": ("молдинг решётки бампера", "Bumper Grille Trim"),
    "tampon-panjur-yuvasi": ("корпус решётки бампера", "Bumper Grille Housing"),
    "tampon-panjuru": ("решётка бампера", "Bumper Grille"),
    "tampon-reflektoru": ("отражатель бампера", "Bumper Reflector"),
    "tampon-takviyesi": ("усилитель бампера", "Bumper Reinforcement"),
    "tampon-traversi": ("поперечина бампера", "Bumper Crossmember"),
    "tampon-ust-parca": ("верхняя часть бампера", "Bumper Upper Section"),
    # --- ремни и цепи ---
    "direksiyon-kayisi": ("ремень гидроусилителя руля", "Power Steering Belt"),
    "triger-gergi-rulmani": ("натяжной ролик ремня ГРМ", "Timing Belt Tensioner"),
    "triger-kayis-seti": ("комплект ремня ГРМ", "Timing Belt Kit"),
    "triger-kayisi": ("ремень ГРМ", "Timing Belt"),
    "triger-zincir-seti": ("комплект цепи ГРМ", "Timing Chain Kit"),
    "triger-zinciri": ("цепь ГРМ", "Timing Chain"),
    "v-kayis-gergi-rulmani": ("натяжной ролик приводного ремня", "Drive Belt Tensioner"),
    "v-kayis-seti": ("комплект приводного ремня", "Drive Belt Kit"),
    "v-kayisi": ("приводной ремень", "Drive Belt"),
    "yag-pompa-zincir-seti": ("комплект цепи масляного насоса", "Oil Pump Chain Kit"),
    "yag-pompa-zinciri": ("цепь масляного насоса", "Oil Pump Chain"),
    # --- масла и жидкости ---
    "antifriz": ("антифриз", "Antifreeze"),
    "bakim-ve-temizlik": ("средство для ухода за автомобилем", "Car Care Product"),
    "motor-bakim-katkilar": ("присадка для двигателя", "Engine Additive"),
    "motor-yag": ("моторное масло", "Engine Oil"),
    # --- топливная система ---
    "adblue-sistemi": ("деталь системы AdBlue", "AdBlue System Part"),
    "depo-samandirasi": ("датчик уровня топлива", "Fuel Level Sender"),
    "egr-sogutucu": ("охладитель EGR", "EGR Cooler"),
    "egr-valfi": ("клапан EGR", "EGR Valve"),
    "enjektor": ("топливная форсунка", "Fuel Injector"),
    "gaz-kelebegi": ("дроссельная заслонка", "Throttle Body"),
    "gaz-kelebegi-sensoru": ("датчик положения дроссельной заслонки", "Throttle Position Sensor"),
    "gaz-pedali": ("педаль газа", "Accelerator Pedal"),
    "gaz-teli": ("трос газа", "Accelerator Cable"),
    "hava-filtre-kutusu-ve-parcalari": ("корпус воздушного фильтра", "Air Filter Housing"),
    "mazot-pompasi": ("топливный насос", "Fuel Pump"),
    "rolanti-ayar-motoru": ("регулятор холостого хода", "Idle Control Valve"),
    "rolanti-ayar-valfi": ("клапан холостого хода", "Idle Air Control Valve"),
    "yakit-basinc-valfi": ("регулятор давления топлива", "Fuel Pressure Regulator"),
    "yakit-filtre-sensoru": ("датчик топливного фильтра", "Fuel Filter Sensor"),
    "yakit-hortumu": ("топливный шланг", "Fuel Hose"),
    "yakit-otomatigi": ("топливный насос", "Fuel Pump"),
    "yuksek-basinc-pompasi": ("топливный насос высокого давления", "High Pressure Fuel Pump"),
}


def kind_key(title) -> str:
    """«Fren Balatası» → ``fren-balatasi`` (как адрес раздела у источника)."""
    return slugify(normalize_ascii_text(str(title or "")))


def find_kind(*titles) -> tuple[str, str] | None:
    """Первый из видов (вид карточки, затем раздел), который есть в словаре."""
    for title in titles:
        kind = PART_KINDS.get(kind_key(title))
        if kind:
            return kind
    return None


# Подписи характеристик с числовым значением: (русская, английская, единица RU, единица EN).
# В описание попадают только они — значения-слова («Ön aks») остаются у источника.
SPEC_LABELS: dict[str, tuple[str, str, str, str]] = {
    "uzunluk": ("Длина", "Length", "мм", "mm"),
    "komple-uzunluk": ("Общая длина", "Overall length", "мм", "mm"),
    "genislik": ("Ширина", "Width", "мм", "mm"),
    "genislik-1": ("Ширина 1", "Width 1", "мм", "mm"),
    "genislik-2": ("Ширина 2", "Width 2", "мм", "mm"),
    "yukseklik": ("Высота", "Height", "мм", "mm"),
    "yukseklik-1": ("Высота 1", "Height 1", "мм", "mm"),
    "yukseklik-2": ("Высота 2", "Height 2", "мм", "mm"),
    "kalinlik": ("Толщина", "Thickness", "мм", "mm"),
    "kalinlik-1": ("Толщина 1", "Thickness 1", "мм", "mm"),
    "kalinlik-2": ("Толщина 2", "Thickness 2", "мм", "mm"),
    "fren-diski-kalinligi": ("Толщина тормозного диска", "Brake disc thickness", "мм", "mm"),
    "asgari-kalinlik": ("Минимальная толщина", "Minimum thickness", "мм", "mm"),
    "cap": ("Диаметр", "Diameter", "мм", "mm"),
    "dis-cap": ("Наружный диаметр", "Outer diameter", "мм", "mm"),
    "ic-cap": ("Внутренний диаметр", "Inner diameter", "мм", "mm"),
    "merkezleme-capi": ("Диаметр центровки", "Centering diameter", "мм", "mm"),
    "delik-cemberi": ("Диаметр расположения отверстий", "Bolt circle diameter", "мм", "mm"),
    "delik-sayisi": ("Число отверстий", "Number of holes", "", ""),
    "dis-sayisi": ("Число зубьев", "Number of teeth", "", ""),
    "kanal-sayisi": ("Число ручьёв", "Number of ribs", "", ""),
    "agirlik": ("Вес", "Weight", "кг", "kg"),
    "gerilim": ("Напряжение", "Voltage", "В", "V"),
    "sarj-akimi": ("Ток заряда", "Charge current", "А", "A"),
    "guc": ("Мощность", "Power", "кВт", "kW"),
    "basinc": ("Давление", "Pressure", "бар", "bar"),
    "acilma-sicakligi": ("Температура открытия", "Opening temperature", "°C", "°C"),
    "sikma-torku": ("Момент затяжки", "Tightening torque", "Н·м", "Nm"),
    "elektrot-araligi": ("Зазор электрода", "Electrode gap", "мм", "mm"),
    "disli-uzunlugu": ("Длина резьбы", "Thread length", "мм", "mm"),
    "anahtar-agzi": ("Размер под ключ", "Spanner size", "мм", "mm"),
    "baglantilarin-sayisi": ("Число контактов", "Number of connectors", "", ""),
}

_NUMERIC_VALUE = re.compile(r"^\d+(?:[.,]\d+)?$")
_UNIT_SUFFIX = re.compile(r"\s*\[[^\]]*\]\s*$")


def translate_spec(label, value) -> tuple[str, str] | None:
    """Числовая характеристика → («Длина: 107 мм», «Length: 107 mm»); остальное — None."""
    text = str(value or "").strip()
    known = SPEC_LABELS.get(kind_key(_UNIT_SUFFIX.sub("", str(label or ""))))
    if not known or not _NUMERIC_VALUE.match(text):
        return None
    ru, en, unit_ru, unit_en = known
    return (
        f"{ru}: {text}{' ' + unit_ru if unit_ru else ''}",
        f"{en}: {text.replace(',', '.')}{' ' + unit_en if unit_en else ''}",
    )


# Марки и бренды, которые пишутся не «С заглавной»: сокращения и составные.
_NAME_SPELLING = {
    "BMW": "BMW", "VW": "VW", "MG": "MG", "DS": "DS", "MAN": "MAN", "DAF": "DAF", "GMC": "GMC",
    "MINI": "MINI", "SMART": "smart", "MERCEDES-BENZ": "Mercedes-Benz", "ALFA ROMEO": "Alfa Romeo",
    "LAND ROVER": "Land Rover", "ROLLS-ROYCE": "Rolls-Royce", "ASTON MARTIN": "Aston Martin",
    "CITROËN": "Citroën", "CITROEN": "Citroën", "ŠKODA": "Škoda", "SKODA": "Škoda", "SSANGYONG": "SsangYong",
    "SWAG": "SWAG", "LUK": "LuK", "SCHAEFFLER LUK": "Schaeffler LuK", "MANN-FILTER": "MANN-FILTER",
    "FEBI": "febi", "FEBI BILSTEIN": "febi bilstein", "BREMBO": "Brembo", "NRF": "NRF",
}


def proper_name(value) -> str:
    """«VOLKSWAGEN» → «Volkswagen», «BLUE PRINT» → «Blue Print»; «BMW», «SKF», «TRW» — как есть.

    Меняются только слова, написанные целиком заглавными и длиннее трёх букв
    («TRANSIT Custom» → «Transit Custom», «Schaeffler LuK» остаётся).
    """
    text = re.sub(r"\s+", " ", str(value or "")).strip().replace("Ё", "Ë")
    if text.upper() in _NAME_SPELLING:
        return _NAME_SPELLING[text.upper()]
    return re.sub(
        r"[^\W\d_]+",
        lambda match: match.group(0).capitalize()
        if len(match.group(0)) > 3 and match.group(0).isupper() else match.group(0),
        text,
    )


def model_name(value, locale: str) -> str:
    """Модель автомобиля: «3 Serisi» → «3 серии» / «3 Series», «S-Serisi» → «S-класса» / «S-Class»."""
    text = proper_name(value)
    text = re.sub(r"\b([A-Z]{1,3})-Serisi\b", r"\1-класса" if locale == "ru" else r"\1-Class", text)
    return re.sub(r"\bSerisi\b", "серии" if locale == "ru" else "Series", text)
