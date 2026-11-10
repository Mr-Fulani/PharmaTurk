# Модерация, круг 6: переводы недостающих абзацев лекарств (10.11.2026)

Пункт 7 владельца. Недостающие абзацы разделов инструкций перевёл Claude прямо в сессии, без API, $0. Каждый перевод прошёл ту же
проверку абзаца, что и переводы конвейера (дозы, бренд, язык, длина). Затем раздел целиком собирается из памяти и проверяется ещё раз.

Переведено **165** абзацев для **45** карточек. Ещё 6 абзацев оставлены человеку, их 7 карточек остаются в модерации:

- #53 — LAXAMOT: в исходнике «mlSonrasında» склеено — проверка не видит единицу дозы (логи 31439)
- #54 — обрывок «LAXAMO» (мусор PDF) (логи 31439)
- #55 — LEVERETTE: число в исходнике испорчено («000 kadından» вместо «10 000») (логи 31409)
- #94 — PSENAC: абзац повторён дважды через «00» (мусор PDF) (логи 30822)
- #102 — SIMLANDI: фраза повторена дважды с цифрами из PDF (логи 30930, 30933, 30934)
- #169 — WINRHO SDF: смысл исходника неясен (про Rh-положительную мать) — нужен человек (логи 31398)

Проверка без записи (10.11, релиз 269a991a): **44 из 45** карточек проходят. У GLISENIT (лог 31140) раздел «Применение» не проходит из-за старой ошибки памяти, запись 336148:
«GLİSENİTile tedavi sonlandırıldığında oluşabilecek etkiler» переведено как «…при прекращении лечения **ГЛИЦЕРОЛОМ**» (EN «…with **GLYCEROL**»). Предлагается: «Эффекты, которые могут возникнуть при прекращении лечения GLISENIT» / «Effects that may occur when treatment with GLISENIT is stopped». После этого проходят все 45.

Правки исходника при переводе:
- SERIDEN DR — в турецком тексте «ROMEZON DR» → «этот препарат» (пилот);
- COUMADIN/WARFMADIN — «WARFMADİN'in etkisini…» → «действие варфарина»;
- IMPLANON — в турецком тексте «NEXPLANON» → «имплантат»;
- NICORETTE — опечатка источника «NICORETTEP®» → «NICORETTE®»; SIPROJECT — «SİRPOJECT» → «SIPROJECT».

## AVMIGRAN (логи 31420)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 26 | Propranolol, oksprenolol, atenolol veya verapamil maddelerini içeren ilaçlar | Препараты, содержащие пропранолол, окспренолол, атенолол или верапамил |
| 27 | Ör: reboksetin, nefazodon, fluoksetin veya fluvoksamin maddelerini içeren ilaçlar | Например, препараты, содержащие ребоксетин, нефазодон, флуоксетин или флувоксамин |

## BRUFEN RETARD (логи 31323)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 28 | BRUFEN®'in içeriğinde bulunan bazı yardımcı maddeler hakkında önemli bilgiler | Важная информация о некоторых вспомогательных веществах в составе BRUFEN® |
| 29 | BRUFEN®, tedavi etmek/önlemek amaçlı kullanılan aşağıdakiler de dahil olmak üzere bazı ilaçlarla tedaviyi etkileyebilir veya bunlardan etkilenebilir. | BRUFEN® может влиять на лечение некоторыми препаратами или подвергаться их влиянию, в том числе препаратами, которые применяются для лечения или профилактики следующего: |
| 30 | Alkol: BRUFEN® baş dönmesi, uyuşukluk ve mide kanaması gibi mide problemleri şeklinde yan etkilere neden olabilir. BRUFEN® ile aşırı alkol alımı bu yan etkileri daha da kötü hale getirebilir.. | Алкоголь: BRUFEN® может вызывать побочные эффекты, такие как головокружение, сонливость и проблемы с желудком, например желудочное кровотечение. Чрезмерное употребление алкоголя во время приёма BRUFEN® может усилить эти побочные эффекты. |

## COUMADIN (логи 31270, 31271)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 31 | WARFMADİN'in etkisini azaltan ilaçlar | Препараты, ослабляющие действие варфарина |

## DEPAKIN (логи 31342)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 32 | Hamilelik oluşmadan önceki 3 aylık dönemde valproat kullandığınız sırada partneriniz hamile kalırsa ve sorularınız mevcutsa doktorunuzla iletişime geçiniz. Doktorunuzla konuşmadan tedavinizi kesmeyiniz. Tedavinizi bırakırsanız, durmunuz kötüye gidebilir. | Если ваша партнёрша забеременела, когда вы принимали вальпроат в течение 3 месяцев до наступления беременности, и у вас есть вопросы, обратитесь к врачу. Не прекращайте лечение, не поговорив с врачом. Если вы прекратите лечение, ваше состояние может ухудшиться. |

## DEPAKIN CHRONO BT (логи 31112)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 33 | DEPAKİN'in içeriğinde bulunan bazı yardımcı maddeler hakkında önemli bilgiler | Важная информация о некоторых вспомогательных веществах в составе DEPAKIN |
| 34 | DEPAKİN, beyin kanaması sonrası oluşabilecek komplikasyonları önlemek için kullanılan nimodipinin etkilerini arttırabilir, | DEPAKIN может усиливать действие нимодипина, который применяется для предотвращения осложнений после кровоизлияния в мозг, |
| 35 | Bu ilaçlar DEPAKİN'in etkisini değiştirebilir ve istenmeyen etkilere yol açabilir. | Эти препараты могут изменять действие DEPAKIN и вызывать нежелательные эффекты. |

## DIANE-35 (логи 31038)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 36 | Bazı kadınlar aknelerden kurtulmak veya bronzlaşmak için solaryum kullanır. Bu, akne (sivilce) için pek faydalı bir tedavi yöntemi değildir. DIANE kullanırken solaryuma girmeyin veya bronzlaşma cihazı kullanmayın ve uzun süre güneşlenmekten kaçının. Bunların kullanımı ciltte lekelenme şeklinde renk değişikliğine neden olan kloazma riskini artırır (normal doğum kontrol ilaçları da bu riski artırır). | Некоторые женщины пользуются солярием, чтобы избавиться от акне или загореть. Это не слишком полезный способ лечения акне (угревой сыпи). Во время применения DIANE не посещайте солярий, не пользуйтесь аппаратами для загара и избегайте длительного пребывания на солнце. Это повышает риск хлоазмы — изменения цвета кожи в виде пятен (обычные противозачаточные таблетки также повышают этот риск). |
| 37 | DIANE kesildikten sonra bazı kadınlarda özellikle önceden bu tip sorunları olanlarda amenore (adet görememe) veya oligomenore (adet gecikmesi) gelişebilir. | После прекращения приёма DIANE у некоторых женщин, особенно если такие проблемы были раньше, может развиться аменорея (отсутствие менструаций) или олигоменорея (задержка менструаций). |
| 38 | DIANE'in yiyecek ve içecek ile kullanılması | Применение DIANE с пищей и напитками |
| 39 | DIANE kullanımı sırasında yiyecek ve içecekler hakkında herhangi özel bir talimat yoktur. | Особых указаний относительно пищи и напитков во время применения DIANE нет. |
| 40 | DIANE, hamilelikte kullanılmamalıdır. DIANE kullanımı sırasında hamilelik meydana gelirse kullanım durdurulmalıdır. Hamile olduğunuzdan şüpheleniyorsanız, DIANE, kullanmayı bırakmadan önce hamilelik testi yaparak durumdan emin olun.. | DIANE нельзя применять во время беременности. Если беременность наступила во время применения DIANE, приём следует прекратить. Если вы подозреваете беременность, перед прекращением приёма DIANE сделайте тест на беременность, чтобы убедиться в этом. |
| 41 | DIANE kullanımının araç ve makine kullanma becerileri üzerinde herhangi bir etkisi yoktur. | Применение DIANE не влияет на способность управлять транспортными средствами и работать с механизмами. |

## ELLEACNELLE (логи 31040)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 42 | Yüksek dozlarda siproteron asetat (günde 25 mg ve üzeri) ile, iyi huylu beyin tümörü (menenjiyom) gelişme riskinde artış bildirilmiştir. Eğer sizde bir menenjiyom tespit edilirse, doktorunuz önlem olarak {BRAND} dahil olmak üzere siproteron asetat içeren tüm tıbbi ürünleri kesecektir (‘2. {BRAND} kullanmadan önce dikkat edilmesi gerekenler' ‘{BRAND}'i aşağıdaki durumlarda KULLANMAYINIZ' başlığına bakınız.). | При применении высоких доз ципротерона ацетата (25 мг в сутки и более) сообщалось о повышении риска развития доброкачественной опухоли головного мозга (менингиомы). Если у вас обнаружат менингиому, врач в качестве меры предосторожности отменит все препараты, содержащие ципротерона ацетат, включая {BRAND} (см. раздел «2. Что следует учесть перед применением {BRAND}», подраздел «Не применяйте {BRAND} в следующих случаях»). |

## EMPAVERA MET (логи 31367)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 43 | Alkol içeren ilaçlar (Bkz. EMPAVERA-MET ve alkolün birlikte kullanılması) | Препараты, содержащие алкоголь (см. «Применение EMPAVERA-MET с алкоголем») |
| 44 | İyotlu kontrast madde içeren ilaçlar (röntgen tetkiki sırasında kullanılan ilaçlar) (Bkz. "EMPAVERA-MET'i aşağıdaki durumlarda dikkatli kullanınız"). | Препараты, содержащие йодсодержащие контрастные вещества (применяются при рентгенологическом исследовании) (см. «Применяйте EMPAVERA-MET с осторожностью в следующих случаях»). |
| 45 | Lityum alıyorsanız. EMPAVERA-MET kanınızdaki lityum miktarını azaltabilir. | Если вы принимаете литий: EMPAVERA-MET может снижать количество лития в крови. |
| 46 | EMPAVERA-MET ve alkolün birlikte kullanılması | Применение EMPAVERA-MET с алкоголем |
| 47 | EMPAVERA-MET alırken, laktik asidoz riskinin artabilmesi nedeni ile aşırı alkol tüketilmesinden kaçınılmalıdır (Bkz. "2. EMPAVERA-MET kullanmadan önce dikkat edilmesi gerekenler"). | Во время приёма EMPAVERA-MET следует избегать чрезмерного употребления алкоголя, так как может повышаться риск лактоацидоза (см. «2. Что следует учесть перед применением EMPAVERA-MET»). |

## ERGAFEIN (логи 31422)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 48 | Depresyon tedasinde kullanılan ilaçlar (reboksetin, nefazodon, fluoksetin veya fluvoksamin vb.) | Препараты для лечения депрессии (ребоксетин, нефазодон, флуоксетин, флувоксамин и др.) |

## GLISENIT (логи 31140)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 49 | Sapropterin (tetrahidrobipterin, BH4) nitrik oksit sentetazının bir kofaktörüdür. Sapropterin içeren ilaçlar (Örn. Kuvan. Kuvan yetişkin ve çocuklar dahil tüm Fenilketonüri, (FKÜ) hastaların Hiperfenilalaninemi (HFA) tedavisinde kullanılır. Kuvan ayrıca erişkinler ve çocuklar dahil Hiperfenilalaninemi (HFA) ve tetrahidrobiopterin (BH4) eksikliğinin tedavisinde de kullanılır); klasik nitrik oksit donörleri de (örneğin gliserol trinitrat (GTN), izosorbit dinitrat (ISDN), izosorbid-5-mononitrat (ISMN) ve diğerleri) dahil olmak üzere metabolizmaya ya da nitrik oksidin (NO) etkisini değiştirebilecek, damar açıcı etkin maddelerle birlikte alınacaksa özellikle dikkat etmelisiniz. | Сапроптерин (тетрагидробиоптерин, BH4) — кофактор синтазы оксида азота. Будьте особенно осторожны, если препараты, содержащие сапроптерин (например, Kuvan; Kuvan применяется для лечения гиперфенилаланинемии (ГФА) у всех пациентов с фенилкетонурией (ФКУ), включая взрослых и детей, а также для лечения гиперфенилаланинемии (ГФА) и дефицита тетрагидробиоптерина (BH4) у взрослых и детей), будут применяться вместе с сосудорасширяющими веществами, которые могут изменять метаболизм или действие оксида азота (NO), включая классические доноры оксида азота (например, глицерилтринитрат (GTN), изосорбида динитрат (ISDN), изосорбида-5-мононитрат (ISMN) и другие). |
| 50 | Gliserol trinitrat ve doku plazminojen aktivatörünün (t-PA) (Alteplase, Reteplase ve Tenecteplase gibi doku plazminojen aktivatörü (t-PA) ürünler, kan pıhtısının sebep olduğu emboli veya inme klinik durumların tedavisinde pıhtının parçalanmasında görev alır) eşzamanlı verilmesi durumunda t-PA'nın plazma konsantrasyonunda azalma ve böylelikle de uygulanan t-PA dozunun etkisinde azalma olabilir.. | При одновременном введении глицерилтринитрата и тканевого активатора плазминогена (t-PA) (препараты t-PA, такие как алтеплаза, ретеплаза и тенектеплаза, растворяют тромбы при эмболии или инсульте, вызванных сгустком крови) концентрация t-PA в плазме может снижаться, а значит, может ослабевать действие введённой дозы t-PA. |

## IMPLANON (логи 31283)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 51 | NEXPLANON yerleştirilmeden önce, doktorunuz sizin ve yakın akrabalarınızın sağlık öyküleri hakkında sorular soracaktır. Doktorunuz aynı zamanda tansiyonunuzu ölçecektir. Kişisel durumunuza bağlı olarak bazı testler de uygulayabilir. NEXPLANON kullanırken, doktorunuz size implant yerleştirildikten bir süre sonra (düzenli) sağlık kontrolleri yaptırmak için kendisine geri dönmenizi söyleyecektir. Bu kontrollerin sıklığı ve bu kontroller sırasında neler yapılacağı, sizin kişisel durumunuza bağlıdır. Doktorunuz, her sağlık kontrolü sırasında, implantı elle kontrol etmelidir. | Перед установкой имплантата врач расспросит вас о состоянии здоровья — вашем и ваших близких родственников. Врач также измерит вам артериальное давление. В зависимости от вашей ситуации могут быть проведены и некоторые анализы. Во время использования имплантата врач попросит вас через некоторое время после установки (регулярно) приходить на медицинские осмотры. Частота этих осмотров и то, что будет при них проводиться, зависят от вашей ситуации. При каждом осмотре врач должен прощупать имплантат рукой. |
| 52 | Eğer kendi sağlığınızda, özellikle bu broşürde sözü edilenlerle ilgili herhangi bir değişiklik fark ederseniz (ayrıca bkz. ‘NEXPLANON'u aşağıdaki durumlarda kullanmayınız' ve ‘NEXPLANON'u aşağıdaki durumlarda dikkatli kullanınız'; yakın aile bireylerinizle ilgili maddeleri unutmayınız); | Если вы заметили какие-либо изменения в своём здоровье, особенно связанные с тем, что упоминается в этой инструкции (см. также «Не применяйте имплантат в следующих случаях» и «Применяйте имплантат с осторожностью в следующих случаях»; не забывайте о пунктах, касающихся ваших близких родственников); |

## LUCRIN DEPOT (логи 31194, 31195)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 56 | -Kan damarlarında ya da kalpte genişleme (anevrizma) | -Расширение кровеносных сосудов или сердца (аневризма) |
| 57 | -Dolaşım sistemindeki bozukluk (sirküler kollaps) | -Нарушение кровообращения (циркуляторный коллапс) |
| 58 | -Dokuda kan birikmesi (hematom) | -Скопление крови в тканях (гематома) |
| 59 | -Kol ve bacaklarda zayıf kan dolaşımı (zayıf periferal dolaşım) | -Плохое кровообращение в руках и ногах (нарушение периферического кровообращения) |
| 60 | -Kan ya da kan lekeli balgamlı öksürük (hemoptizi) | -Кашель с кровью или мокротой с примесью крови (кровохарканье) |
| 61 | -Akciğer dokusunun esnekliğinin kaybına bağlı şiddetli nefes darlığı ile sonuçlanan akciğer hastalığı (amfizem) | -Заболевание лёгких, при котором из-за потери эластичности лёгочной ткани возникает сильная одышка (эмфизема) |
| 62 | -KOAH (Kronik obstrüktif akciğer hastalığı) (Bronşlarda kalıcı ve ilerleyici tıkanıklığa bağlı kronik akciğer hastalığı) | -ХОБЛ (хроническая обструктивная болезнь лёгких) (хроническое заболевание лёгких, связанное со стойкой и прогрессирующей закупоркой бронхов) |
| 63 | -Üst karın bölgesinde hassasiyet, ağrı, dışkı renginde açılma (karaciğer iltihaplanması) (kolestatik hepatit) | -Болезненность, боль в верхней части живота, посветление кала (воспаление печени) (холестатический гепатит) |
| 64 | -Karaciğer hücrelerinin hasar görmesi (hepatoselüler hasar) | -Повреждение клеток печени (гепатоцеллюлярное повреждение) |
| 65 | -Kırmızı lekeler ve şişliklerle döküntü (makülopapüler döküntü) | -Сыпь с красными пятнами и припухлостями (макулопапулёзная сыпь) |
| 66 | -Kırmızı kan hücrelerinde sedimentasyon (çökme) hızı artışı | -Повышение скорости седиментации (оседания) эритроцитов |
| 67 | -Varis | -Варикоз |

## MEKINIST (логи 31304)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 68 | Eğer bu kullanma talimatında bahsi geçmeyen herhangi bir yan etki ile karşılaşırsanız doktorunuzu, eczacınızı veya hemşirenizi bilgilendiriniz. Buna, bu ya da dabrafenib kullanma talimatında bahsi geçmeyen tüm olası yan etkiler dahildir. | Если у вас возникнет побочный эффект, не упомянутый в этой инструкции, сообщите об этом врачу, фармацевту или медсестре. Это касается любых возможных побочных эффектов, не упомянутых ни в этой инструкции, ни в инструкции к дабрафенибу. |

## NICORETTE FRESHMINT (логи 31034, 31035, 31392, 31423)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 69 | Eğer NICORETTEP® FRESHMINT'in etkisinin çok güçlü veya zayıf olduğuna dair bir izleniminiz varsa doktorunuz veya eczacınız ile konuşunuz. | Если вам кажется, что действие NICORETTE® FRESHMINT слишком сильное или слишком слабое, поговорите с врачом или фармацевтом. |
| 70 | Kullanmanız gerekenden daha fazla NICORETTE® FRESHMINT kullandıysanız | Если вы применили NICORETTE® FRESHMINT больше, чем следует |
| 71 | Eğer almanız gereken adetten fazla sayıda NICORETTEP® FRESHMINT kullanırsanız bulantı (kendini hasta hissetme), kusma, tükürük artışı, karın ağrısı, ishal, terleme, baş ağrısı, baş dönmesi, duyma güçlüğü veya belirgin güçsüzlük duyabilirsiniz. Daha yüksek dozların alındığı vakalarda bu semptomları takiben hipotansiyon, zayıf veya düzensiz nabız, solunum güçlüğü, bitkinlik, dolaşım kolapsı ve genel konvülsiyonlar gelişebilir. Bu durumda nikotin alımı hemen durdurulmalı ve en yakın hastaneye başvurulmalıdır. Doktora veya hastaneye gittiğinizde bu kullanma talimatını ve sakızın ambalajını yanınızda götürünüz. | Если вы использовали больше жевательных резинок NICORETTE® FRESHMINT, чем положено, у вас могут появиться тошнота (плохое самочувствие), рвота, усиленное слюноотделение, боль в животе, диарея, потливость, головная боль, головокружение, нарушение слуха или выраженная слабость. При приёме более высоких доз за этими симптомами могут последовать гипотензия, слабый или нерегулярный пульс, затруднённое дыхание, сильная усталость, циркуляторный коллапс и генерализованные судороги. В этом случае следует немедленно прекратить поступление никотина и обратиться в ближайшую больницу. Отправляясь к врачу или в больницу, возьмите с собой эту инструкцию и упаковку жевательной резинки. |
| 72 | NICORETTEP® FRESHMINT'tan kullanmanız gerekenden fazlasını kullanmışsanız bir doktor veya eczacı ile konuşunuz. | Если вы применили NICORETTE® FRESHMINT больше, чем следует, поговорите с врачом или фармацевтом. |
| 73 | NICORETTE® FRESHMINT‘u kullanmayı unutursanız | Если вы забыли применить NICORETTE® FRESHMINT |
| 74 | NICORETTE® FRESHMINT ile tedavi sonlandırıldığında oluşabilecek etkiler | Что может произойти после прекращения лечения NICORETTE® FRESHMINT |
| 75 | Belirlenen tedavi süreniz tamamlanmadan NICORETTEP® FRESHMINT‘u bırakırsanız, tedaviniz başarılı olamayabilir. | Если вы прекратите применять NICORETTE® FRESHMINT до окончания назначенного курса, лечение может оказаться безуспешным. |

## NOVOPLAN (логи 31176)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 76 | NOVO-PLAN'ın içeriğinde bulunan bazı yardımcı maddeler hakkında önemli bilgiler | Важная информация о некоторых вспомогательных веществах в составе NOVO-PLAN |
| 77 | Özellikle, kan seviyelerini düşürebilecek ve NOVO-PLAN'ın etkisini azaltabilecek aşağıdaki ilaçları doktorunuza söyleyin: | В частности, сообщите врачу о следующих препаратах, которые могут снижать уровень в крови и ослаблять действие NOVO-PLAN: |
| 78 | Özellikle, NOVO-PLAN`ı etkileyen veya etkileyebilecek olan aşağıdaki ilaçları doktorunuza söyleyin. | В частности, сообщите врачу о следующих препаратах, которые влияют или могут влиять на NOVO-PLAN. |
| 79 | NOVO-PLAN'ın dahil olduğu ilaç grubu olan pirazolonların kullanımı, diğer bazı ilaçlarla etkileşimlere yol açabilir: | Применение пиразолонов — группы препаратов, к которой относится NOVO-PLAN, — может приводить к взаимодействию с некоторыми другими препаратами: |
| 80 | NOVO-PLAN`ın bu etkileşimlere ne ölçüde neden olduğu bilinmemektedir. | Неизвестно, в какой степени NOVO-PLAN вызывает эти взаимодействия. |
| 81 | Eğer NOVO-PLAN enjeksiyonluk çözelti kullanıyorsanız, herhangi bir laboratuvar testi (örneğin kreatinin, yağ, HDL-kolesterol veya ürik asit testleri) yaptırmadan önce doktorunuzu bilgilendiriniz, çünkü metamizol bazı sonuçları etkileyebilir. | Если вы применяете NOVO-PLAN раствор для инъекций, сообщите врачу перед любым лабораторным анализом (например, на креатинин, жиры, холестерин ЛПВП или мочевую кислоту), так как метамизол может влиять на некоторые результаты. |

## NUVARING VAGINAL (логи 31412)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 82 | NUVARING kullanımı sırasında yukarıdaki durumlardan herhangi biri değişirse, örneğin, yakın akrabalarınızdan birinde sebebi belli olmayan tromboz gerçekleşirse veya fazla kilo alırsanız, doktorunuza söyleyiniz. | Если во время применения NUVARING какое-либо из перечисленных выше обстоятельств изменится, например у кого-то из ваших близких родственников случится тромбоз без явной причины или вы сильно наберёте вес, сообщите об этом врачу. |
| 83 | NUVARING kullanımıyla kalp krizi veya inme riski oldukça düşüktür ancak aşağıdaki durumlarda bu risk artar: | Риск инфаркта или инсульта при применении NUVARING очень низкий, однако он повышается в следующих случаях: |
| 84 | sigara kullanıyorsanız. NUVARING gibi kombine hormonal kontraseptif kullanırken sigarayı bırakmanız önerilir. Sigara kullanmayı bırakamıyorsanız ve 35 yaş üzerindeyseniz doktorunuz farklı bir doğum kontrol yöntemi kullanmanızı önerebilir; | если вы курите. При применении комбинированного гормонального контрацептива, такого как NUVARING, рекомендуется бросить курить. Если вы не можете бросить курить и вам больше 35 лет, врач может посоветовать другой метод контрацепции; |
| 85 | NUVARING kullanımı sırasında yukarıdaki durumlardan herhangi biri değişirse, örneğin, sigara kullanmaya başlarsanız veya yakın akrabalarınızdan birinde sebebi belli olmayan tromboz gerçekleşirse veya fazla kilo alırsanız, doktorunuza söyleyiniz. | Если во время применения NUVARING какое-либо из перечисленных выше обстоятельств изменится, например вы начнёте курить, у кого-то из ваших близких родственников случится тромбоз без явной причины или вы сильно наберёте вес, сообщите об этом врачу. |
| 86 | Aşağıdaki bilgiler kombine doğum kontrol haplarıyla yapılan çalışmalarda elde edilmiştir ve NUVARING için de geçerli olabilir. Gebelik önleyici hormonların vajinal yoldan kullanılmasıyla ilişkili bilgiler (NUVARING gibi) mevcut değildir.. | Приведённые ниже сведения получены в исследованиях комбинированных противозачаточных таблеток и могут относиться также к NUVARING. Сведений о противозачаточных гормонах, применяемых влагалищно (таких как NUVARING), нет. |
| 87 | Size NUVARING reçetesi yazan doktora her zaman, kullanmakta olduğunuz ilaçları veya bitkisel ilaçları söyleyiniz. Ayrıca size diğer bir ilaç için reçete yazan diğer herhangi bir doktora veya diş hekimine (ya da eczacıya), NUVARING kullanmakta olduğunuzu söyleyiniz. Bu kişiler size, başka ilave bir doğum kontrol yöntemi (örneğin prezervatif) kullanmanıza ihtiyaç olup olmadığını ve eğer ihtiyaç varsa bunun, ne süre uygulanması gerektiğini veya ihtiyacınız olan diğer ilacın kullanımının değiştirilip değiştirilmeyeceğini söyleyebilirler. | Всегда сообщайте врачу, который назначает вам NUVARING, какие препараты или растительные средства вы принимаете. Также сообщайте любому другому врачу или стоматологу (или фармацевту), который назначает вам другой препарат, что вы применяете NUVARING. Они могут сказать, нужен ли вам дополнительный метод контрацепции (например, презерватив) и если нужен, то как долго, или нужно ли изменить применение другого препарата, который вам требуется. |
| 88 | Eğer bir menstruasyon (adet) döneminiz gerçekleşmemişse, ancak NUVARING kullanma talimatını yerine getirmiş ve başka ilaçlar kullanmamışsanız, gebe olma olasılığınız çok düşüktür. NUVARING kullanmaya her zamanki gibi devam ediniz. Eğer ikinci kez menstruasyon döneminiz de gerçekleşmezse, gebe olabilirsiniz. Hemen doktorunuza danışınız. Doktorunuz hamile olmadığınızı kontrol edene kadar sonraki NUVARING'e başlamayınız. | Если у вас не было менструации, но вы соблюдали инструкцию по применению NUVARING и не принимали других препаратов, вероятность беременности очень мала. Продолжайте применять NUVARING как обычно. Если менструации не будет и во второй раз, возможно, вы беременны. Сразу обратитесь к врачу. Не начинайте следующее кольцо NUVARING, пока врач не убедится, что вы не беременны. |
| 89 | NUVARING kullanma talimatını yerine getirmemişseniz | Если вы не соблюдали инструкцию по применению NUVARING |
| 90 | Bir menstruasyon döneminiz gerçekleşmemişse, NUVARING kullanma talimatını yerine getirmemişseniz ve ilk normal halkasız dönemde de beklenen menstruasyon kanamanız gerçekleşmezse, gebe olabilirsiniz. Yeni bir NUVARING halkasına başlamadan önce doktorunuza danışınız.. | Если у вас не было менструации, вы не соблюдали инструкцию по применению NUVARING и ожидаемое менструальное кровотечение не наступило и в первый обычный перерыв без кольца, возможно, вы беременны. Перед тем как начать новое кольцо NUVARING, обратитесь к врачу. |
| 91 | Bazı kadınlarda NUVARING kullanırken, menstruasyon dönemleri arasında beklenmedik vajinal kanama görülebilir. Hijyenik ped kullanmanız gerekebilir. Ne olursa olsun, halkayı vajinada bırakınız ve normal olarak halkayı kullanmaya devam ediniz. Düzensiz kanamalarınız devam ederse, şiddetlenirse veya yeniden başlarsa, doktorunuza bildiriniz. | У некоторых женщин во время применения NUVARING между менструациями может появляться неожиданное влагалищное кровотечение. Возможно, вам понадобятся гигиенические прокладки. В любом случае оставьте кольцо во влагалище и продолжайте применять его как обычно. Если нерегулярные кровотечения продолжаются, усиливаются или возобновляются, сообщите врачу. |
| 92 | Eğer NUVARING kullanma talimatını yerine getirirseniz, menstruasyon döneminiz halkasız dönemde başlayacaktır. Eğer bu başlama gününü değiştirmek isterseniz, halkasız dönemi kısaltabilirsiniz (ama asla uzatamazsınız!). | Если вы соблюдаете инструкцию по применению NUVARING, менструация начнётся в перерыв без кольца. Если вы хотите изменить день её начала, перерыв без кольца можно сократить (но ни в коем случае не удлинять!). |

## PNEMOX (логи 31093)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 93 | Bazı antihistaminikler (örneğin; terfenadin, astemizol, mizolastin), | Некоторые антигистаминные препараты (например, терфенадин, астемизол, мизоластин), |

## QLAIRISTA (логи 31264)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 95 | Sarı kantaron otu (St John's wort) | Зверобой продырявленный (St John's wort) |

## RACE PLUS (логи 31381, 31382)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 96 | RACE® PLUS ile etkileşime girebileceğinden aşağıdaki ilaçları kullanıyorsanız doktorunuzu bilgilendiriniz: | Сообщите врачу, если вы принимаете следующие препараты, так как они могут взаимодействовать с RACE® PLUS: |
| 97 | Şeker hastalığı tedavisinde kullanılan ağız yoluyla alınan şeker düşürücüler ve insülin gibi ilaçlar (RACE® PLUS tedavisi sırasında kan şekeri düzeylerinizi yakından takip ediniz) | Препараты для лечения сахарного диабета, такие как пероральные сахароснижающие средства и инсулин (во время лечения RACE® PLUS внимательно следите за уровнем сахара в крови) |
| 98 | RACE® PLUS ile birlikte vildagliptin (ağız yoluyla kullanılan bir şeker düşürücü) ya da temsirolimus, everolimus, sirolimus gibi (kanser ve organ nakli tedavisinde kullanılır) ilaçlar kullanıyorsanız, anjiyoödem (yüz, dudaklar, gözler veya boğazda şişme) gelişme riski artabilir. | Если вместе с RACE® PLUS вы принимаете вилдаглиптин (пероральное сахароснижающее средство) или такие препараты, как темсиролимус, эверолимус, сиролимус (применяются для лечения рака и при трансплантации органов), может повышаться риск ангионевротического отёка (отёка лица, губ, глаз или горла). |
| 99 | Lityum (ruh sağlığı problemleri için kullanılır). RACE® PLUS, kanınızdaki lityum miktarını artırabilir. Doktorunuz kanınızdaki lityum miktarını yakından takip etmek isteyecektir. | Литий (применяется при психических расстройствах). RACE® PLUS может повышать количество лития в крови. Врач будет внимательно контролировать уровень лития в крови. |
| 100 | Eğer anti-doping testine giren bir sporcuysanız, RACE® PLUS bu testte pozitif bir sonuç verebilir. | Если вы спортсмен и проходите допинг-контроль, RACE® PLUS может дать положительный результат теста. |

## RITALINE (логи 31219)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 101 | Bir dopamin geri alım inhibitörü olarak RİTALİN, dopamin düzeylerini etkileyen ilaçlarla (dopamin agonistleri (DOPA ve trisiklik antidepresanlar dahil) ve dopamin antagonistleri (haloperidol gibi antipsikotikler)) eşzamanlı uygulandığında etkileşime girebilir. RİTALİN'in antipsikotiklerle aynı anda alınması önerilmez çünkü her biri zıt yönde etki gösterir. | Как ингибитор обратного захвата дофамина RITALIN может взаимодействовать с препаратами, влияющими на уровень дофамина, при одновременном применении: с агонистами дофамина (включая ДОФА и трициклические антидепрессанты) и антагонистами дофамина (антипсихотиками, такими как галоперидол). Одновременно принимать RITALIN с антипсихотиками не рекомендуется, так как они действуют в противоположных направлениях. |

## SIPROJECT (логи 31164)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 103 | Aşağıdaki ilaçların vücudunuzda, siprofloksasin ile etkileşime girdiği bilinmektedir. Bazı ilaçlar ile birlikte kullanıldığında SİRPOJECT'in ya da kullanılan diğer ilacın etkisi değişebilir. Bu durum yan etkilerin yaşanma olasılığını da artırmaktadır. Aşağıdaki ilaçları kullanıyorsanız lütfen doktorunuza söyleyiniz: | Известно, что следующие препараты взаимодействуют в организме с ципрофлоксацином. При применении вместе с некоторыми препаратами действие SIPROJECT или другого препарата может изменяться. Это также повышает вероятность побочных эффектов. Если вы принимаете следующие препараты, сообщите об этом врачу: |

## SPORANOX (логи 31385)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 104 | Varfarin gibi kumarinler (kan pıhtıları için kullanılır) | Кумарины, такие как варфарин (применяются при тромбах) |
| 105 | Digoksin (atriyal fibrilasyon için kullanılır) | Дигоксин (применяется при фибрилляции предсердий) |
| 106 | Nadolol (akciğerlerdeki kan damarlarında artan kan basıncı olarak tanımlanan pulmoner hipertansiyon veya göğüste sıkıştırıcı ağrı ile seyreden kalp hastalığı olarak tanımlanan anjina için kullanılır) | Надолол (применяется при лёгочной гипертензии — повышенном давлении в сосудах лёгких — или при стенокардии — заболевании сердца, протекающем со сжимающей болью в груди) |
| 107 | Mide problemleri veya ishal tedavisinde kullanılan ilaçlar | Препараты для лечения проблем с желудком или диареи |
| 108 | Aprepitant veya netupitant (kanser tedavisi sırasında mide bulantısı ve kusma için kullanılır) | Апрепитант или нетупитант (применяются при тошноте и рвоте во время лечения рака) |
| 109 | Loperamid (ishal için kullanılır) | Лоперамид (применяется при диарее) |
| 110 | Alüminyum, kalsiyum, magnezyum veya sodyum bikarbonat gibi antasitler; simetidin, ranitidin gibi H2 reseptör antagonistleri ve lansoprazol, omeprazol, rabeprazol gibi proton pompası inhibitörleri (mide asidi problemlerinin tedavisinde kullanılır) | Антациды, такие как алюминий, кальций, магний или натрия гидрокарбонат; блокаторы H2-рецепторов, такие как циметидин, ранитидин, и ингибиторы протонной помпы, такие как лансопразол, омепразол, рабепразол (применяются для лечения проблем с кислотностью желудка) |
| 111 | Uyku problemleri veya ruh sağlığı problemlerinin tedavisinde kullanılan ilaçlar | Препараты для лечения нарушений сна или психических расстройств |
| 112 | Alprazolam, brotizolam, buspiron veya midazolam (damar yoluyla enjekte edildiğinde) (anksiyeteyi (kaygıyı) gidermede ve uyumanıza yardımcı olmak için kullanılır) | Алпразолам, бротизолам, буспирон или мидазолам (при внутривенном введении) (применяются для снятия тревоги и помощи при засыпании) |
| 113 | Zopiklon (uyumanıza yardımcı olmak için kullanılır) | Зопиклон (применяется, чтобы помочь уснуть) |
| 114 | Alfentanil, buprenorfin, oksikodon veya sufentanil (ağrı için kullanılır) | Алфентанил, бупренорфин, оксикодон или суфентанил (применяются при боли) |

## SYMBICORT TURBUHALER (логи 31300, 31301)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 115 | İlaç başlandıktan sonra ilk üç ay doktorunuz sizi yakından takip edecektir. SYMBICORT® ile tedavi sırasında, astımla ilişkili yan etkiler ve alevlenmeler görülebilir. Böyle bir durumda SYMBICORT® ile tedaviye devam etmeniz, fakat SYMBICORT®'a başlandıktan sonra astım belirtileri kontrol altına alınamazsa veya kötüleşirse tıbbi destek almanız gerekir. | В первые три месяца после начала лечения врач будет внимательно наблюдать за вами. Во время лечения SYMBICORT® могут возникать побочные эффекты и обострения, связанные с астмой. В этом случае продолжайте лечение SYMBICORT®, но если после начала применения SYMBICORT® симптомы астмы не удаётся взять под контроль или они ухудшаются, обратитесь за медицинской помощью. |
| 116 | Eğer SYMBICORT® TURBUHALER®'in etkisinin çok güçlü veya zayıf olduğuna dair bir izleniminiz var ise doktorunuz veya eczacınız ile konuşunuz. | Если вам кажется, что действие SYMBICORT® TURBUHALER® слишком сильное или слишком слабое, поговорите с врачом или фармацевтом. |
| 117 | Kullanmanız gerekenden daha fazla SYMBICORT® TURBUHALER® kullandıysanız | Если вы применили SYMBICORT® TURBUHALER® больше, чем следует |
| 118 | SYMBICORT® TURBUHALER®'den kullanmanız gerekenden fazlasını kullanmışsanız, derhal bir doktor veya eczacı ile konuşunuz. | Если вы применили SYMBICORT® TURBUHALER® больше, чем следует, немедленно поговорите с врачом или фармацевтом. |
| 119 | SYMBICORT® TURBUHALER®'i kullanmanız gerekenden fazla kullandığınızda en sıklıkla oluşabilecek belirtiler titreme, baş ağrısı veya kalbinizin hızlı çarpmasıdır. | Чаще всего при применении SYMBICORT® TURBUHALER® в большем количестве, чем следует, возникают дрожь, головная боль или учащённое сердцебиение. |
| 120 | Eğer SYMBICORT® TURBUHALER®'i almayı unutursanız | Если вы забыли применить SYMBICORT® TURBUHALER® |
| 121 | Eğer almanız gereken bir SYMBICORT® TURBUHALER® dozunu almayı unutursanız, hatırlar hatırlamaz dozunuzu alınız. Ancak neredeyse bir sonraki doz zamanı gelmişse, unutulan dozu atlayınız. | Если вы забыли принять дозу SYMBICORT® TURBUHALER®, примите её, как только вспомните. Однако если почти подошло время следующей дозы, пропустите забытую дозу. |

## TRINITY (логи 31139)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 122 | Sapropterin (tetrahidrobipterin, BH4) nitrik oksit sentetazının bir kofaktörüdür. Sapropterin içeren ilaçlar (ör. kuvan. Kuvan yetişkin ve çocuklar dahil tüm fenilketonüri, (FKÜ) hastaların hiperfenilalaninemi (HFA) tedavisinde kullanılır. Kuvan ayrıca erişkinler ve çocuklar dahil hiperfenilalaninemi (HFA) ve tetrahidrobiopterin (BH4) eksikliğinin tedavisinde de kullanılır); klasik nitrik oksit donörleri de (örneğin gliseril trinitrat (GTN), izosorbit dinitrat (ISDN), izosorbid-5-mononitrat (ISMN) ve diğerleri) dahil olmak üzere metabolizmaya ya da nitrik oksidin (NO) etkisini değiştirebilecek, damar açıcı etkin maddelerle birlikte alınacaksa özellikle dikkat etmelisiniz. | Сапроптерин (тетрагидробиоптерин, BH4) — кофактор синтазы оксида азота. Будьте особенно осторожны, если препараты, содержащие сапроптерин (например, Kuvan; Kuvan применяется для лечения гиперфенилаланинемии (ГФА) у всех пациентов с фенилкетонурией (ФКУ), включая взрослых и детей, а также для лечения гиперфенилаланинемии (ГФА) и дефицита тетрагидробиоптерина (BH4) у взрослых и детей), будут применяться вместе с сосудорасширяющими веществами, которые могут изменять метаболизм или действие оксида азота (NO), включая классические доноры оксида азота (например, глицерилтринитрат (GTN), изосорбида динитрат (ISDN), изосорбида-5-мононитрат (ISMN) и другие). |

## TURKTIPSAN FUROSEMID (логи 31015)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 1 | Aspirin dahil nonsteroidal antiinflamatuvar ilaçlar (ağrı kesici ve iltihap giderici). Bu ilaçlar TURKTIPSAN FUROSEMİD'in etkisini azaltabilir. TURKTIPSAN FUROSEMİD tedavisi dolaşımdaki hacimde azalmaya veya vücut sıvısında eksikliğe neden olursa bu ilaçlarla birlikte kullanımı akut böbrek yetmezliğine sebep olabilir. | Нестероидные противовоспалительные препараты, включая аспирин (обезболивающие и противовоспалительные средства). Эти препараты могут ослаблять действие TURKTIPSAN FUROSEMID. Если лечение TURKTIPSAN FUROSEMID привело к уменьшению объёма циркулирующей крови или к недостатку жидкости в организме, совместное применение с этими препаратами может вызвать острую почечную недостаточность. |
| 2 | Fenitoin (sara hastalığının tedavisinde kullanılır). Bu ilaç TURKTIPSAN FUROSEMİD'in etkisini azaltabilir. | Фенитоин (применяется для лечения эпилепсии). Этот препарат может ослаблять действие TURKTIPSAN FUROSEMID. |
| 3 | Probenesid (gut-damla hastalığında kullanılır). TURKTIPSAN FUROSEMİD bu ilacın böbrek yoluyla atılımını azaltabilir. Dolayısıyla yüksek dozlu tedavide, ilacın kandaki seviyesi artarak yan etkilerin görülme riskinde artışa neden olabilir. | Пробенецид (применяется при подагре). TURKTIPSAN FUROSEMID может замедлять выведение этого препарата почками. Поэтому при лечении высокими дозами его уровень в крови может повышаться, что увеличивает риск побочных эффектов. |
| 4 | Metotreksat (kanser tedavisinde kullanılır). TURKTIPSAN FUROSEMİD bu ilacın böbrek yoluyla atılımını azaltabilir. Dolayısıyla yüksek dozlu tedavide, ilacın kandaki seviyesi artarak yan etkilerin görülme riskinde artışa neden olabilir. | Метотрексат (применяется для лечения рака). TURKTIPSAN FUROSEMID может замедлять выведение этого препарата почками. Поэтому при лечении высокими дозами его уровень в крови может повышаться, что увеличивает риск побочных эффектов. |
| 5 | Şeker hastalığı tedavisinde kullanılan ilaç TURKTIPSAN FUROSEMİD bu ilaçların etkisini azaltabilir. | Препараты для лечения сахарного диабета: TURKTIPSAN FUROSEMID может ослаблять их действие. |
| 6 | Kan basıncını arttıran sempatomimetik ilaçlar (adrenalin benzeri ilaçlar, örneğin epinefrin, norepinefrin). TURKTIPSAN FUROSEMİD bu ilaçların etkisini azaltabilir. | Симпатомиметики, повышающие артериальное давление (адреналиноподобные препараты, например эпинефрин, норэпинефрин). TURKTIPSAN FUROSEMID может ослаблять действие этих препаратов. |
| 7 | Kürar-tipi kas gevşeticiler. TURKTIPSAN FUROSEMİD bu ilaçların etkisini arttırabilir. | Курареподобные миорелаксанты. TURKTIPSAN FUROSEMID может усиливать действие этих препаратов. |
| 8 | Teofilin (solunum ile ilgili hastalıkların tedavisinde kullanılır). TURKTIPSAN FUROSEMİD bu ilacın etkisini arttırabilir. | Теофиллин (применяется для лечения заболеваний дыхательных путей). TURKTIPSAN FUROSEMID может усиливать действие этого препарата. |
| 9 | Böbrek üzerinde zararlı etkisi olan ilaçlar (nefrotoksik ilaçlar) (örneğin aminoglikozidler, sefalosporinler, polimiksinler gibi antibiyotikler). TURKTIPSAN FUROSEMİD bu ilaçların zararlı etkilerini arttırabilir. TURKTIPSAN FUROSEMİD ile aynı zamanda bazı sefalosporinleri yüksek dozda kullanan hastalarda böbrek fonksiyonları bozulabilir. | Препараты, оказывающие вредное действие на почки (нефротоксичные препараты), например антибиотики: аминогликозиды, цефалоспорины, полимиксины. TURKTIPSAN FUROSEMID может усиливать вредное действие этих препаратов. У пациентов, которые одновременно с TURKTIPSAN FUROSEMID получают высокие дозы некоторых цефалоспоринов, может нарушаться функция почек. |
| 10 | Siklosporin A (organ nakilleri sırasında kullanılır). TURKTIPSAN FUROSEMİD neden olduğu kandaki ürik asit seviyelerinin artmasına ve siklosporin ürik asidin üre atılımının bozulmasına neden olur. Bunun sonucunda, guta bağlı olarak artrit riskinde artış olabilir. | Циклоспорин A (применяется при трансплантации органов). TURKTIPSAN FUROSEMID повышает уровень мочевой кислоты в крови, а циклоспорин нарушает её выведение. В результате может повышаться риск артрита, связанного с подагрой. |
| 11 | Böbrek yetmezliği açısından yüksek risk taşıyan hastalarda röntgen tetkiklerinde organların görünürlüğünü arttırmak için kullanılan kontrast maddeler. Kontrast maddelerle tetkik sonrasında, TURKTIPSAN FUROSEMİD ile tedavi gören hastalarda, öncesinde sadece damar içi sıvı alan hastalara kıyasla böbrek fonksiyonlarında daha sık oranda bozulma olmuştur. | Контрастные вещества, которые применяются при рентгенологических исследованиях для лучшей видимости органов, у пациентов с высоким риском почечной недостаточности. После исследования с контрастным веществом у пациентов, получавших TURKTIPSAN FUROSEMID, нарушение функции почек возникало чаще, чем у пациентов, которым перед исследованием вводили только внутривенную жидкость. |
| 12 | Yüksek dozlarda TURKTIPSAN FUROSEMİD ile eş zamanlı olarak tiroid hormonları (örn. levotiroksin) kullanılması tiroid hormonu seviyelerini etkileyebilir. Bu sebeple, TURKTIPSAN FUROSEMİD ile birlikte tiroid hormonu kullanıyorsanız, doktorunuz tiroid hormon seviyelerinizi takip edecektir. | Одновременное применение высоких доз TURKTIPSAN FUROSEMID и гормонов щитовидной железы (например, левотироксина) может влиять на уровень гормонов щитовидной железы. Поэтому, если вы принимаете гормоны щитовидной железы вместе с TURKTIPSAN FUROSEMID, врач будет контролировать их уровень. |
| 13 | Glikozidler (kalp hastalıklarında kullanılır). TURKTIPSAN FUROSEMİD tedavisi sırasında potasyum veya magnezyum eksikliği gelişirse, kalp kasının bu ilaçlara hassasiyeti artabilir. Elektrolit dengesizliği olan hastalarda ve TURKTIPSAN FUROSEMİD'in belli EKG değişikliklerine (QT aralığının uzaması) neden olan ilaçlarla (örneğin, terfenadin, antialerjik ilaçlar ve kalp ritmi bozukluklarında kullanılan bazı ilaçlar (sınıf I ve III antiaritmikler)) birlikte kullanılması durumunda, kalp ritmi bozukluklarının (torsades de pointes dahil venrtiküler artimi) oluşma riski daha yüksektir. | Гликозиды (применяются при заболеваниях сердца). Если во время лечения TURKTIPSAN FUROSEMID развивается недостаток калия или магния, чувствительность сердечной мышцы к этим препаратам может повышаться. У пациентов с нарушением электролитного баланса, а также при применении TURKTIPSAN FUROSEMID вместе с препаратами, вызывающими определённые изменения ЭКГ (удлинение интервала QT), например терфенадином, противоаллергическими препаратами и некоторыми препаратами для лечения нарушений сердечного ритма (антиаритмики классов I и III), риск нарушений сердечного ритма (включая желудочковую аритмию типа «пируэт», torsades de pointes) выше. |
| 14 | Karbamazepin (sara hastalığının tedavisinde kullanılır) veya aminoglutetimid (Cushing Sendromu isimli hastalığın tedavisinde kullanılır). TURKTIPSAN FUROSEMİD ile eşzamanlı kullanılması hiponatremi (kanda sodyum düzeyinin normalin altına düşmesi) riskini arttırabilir. | Карбамазепин (применяется для лечения эпилепсии) или аминоглутетимид (применяется для лечения синдрома Кушинга). Одновременное применение с TURKTIPSAN FUROSEMID может повышать риск гипонатриемии (снижения уровня натрия в крови ниже нормы). |
| 15 | Tiyazidler (idrar söktürücü sınıfında yer alan bir ilaç grubu). TURKTIPSAN FUROSEMİD ile birlikte kullanıldıklarında idrar çıkışında artış meydana gelir. | Тиазиды (группа мочегонных препаратов). При применении вместе с TURKTIPSAN FUROSEMID увеличивается выделение мочи. |
| 16 | Metformin (şeker hastalığında kullanılan bir ilaç). Bu ilaç TURKTIPSAN FUROSEMİD'in etkisini azaltabilir. | Метформин (препарат для лечения сахарного диабета). Этот препарат может ослаблять действие TURKTIPSAN FUROSEMID. |
| 17 | Fibrik asit türevleri (kandaki yağı azaltmada kullanılan ilaçlar örneğin, klofibrat ve fenofibrat). Özellikle hipoalbuminemi durumunda (kandaki albüminde düşüş) TURKTIPSAN FUROSEMİD ile birlikte kullanılmaları durumunda, her iki ilacın da kandaki seviyeleri yükselebilir. Kan seviyeleri takip edilmelidir. | Производные фиброевой кислоты (препараты для снижения уровня жиров в крови, например клофибрат и фенофибрат). При применении вместе с TURKTIPSAN FUROSEMID, особенно при гипоальбуминемии (снижении уровня альбумина в крови), уровень обоих препаратов в крови может повышаться. Необходимо контролировать их уровень в крови. |

## TURKTIPSAN MOKSIFLOKSASIN (логи 31095)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 18 | Eğer hamile iseniz, TURKTIPSAN MOKSİFLOKSASİN'i kullanmamalısınız. | Если вы беременны, вам нельзя применять TURKTIPSAN MOKSIFLOKSASIN. |
| 19 | Bebeğinizi emziriyorsanız, TURKTIPSAN MOKSİFLOKSASİN kullanmamalısınız. | Если вы кормите ребёнка грудью, вам нельзя применять TURKTIPSAN MOKSIFLOKSASIN. |
| 20 | TURKTIPSAN MOKSİFLOKSASİN sizde baş dönmesi veya sersemlik hali oluşturabilir, ani ve geçici görüş kaybına neden olabilir veya kısa süreli kendinizden geçmenize neden olabilir. Böyle bir durum söz konusu ise, TURKTIPSAN MOKSİFLOKSASİN tedavisinde iken araç ya da makine kullanmamalısınız. | TURKTIPSAN MOKSIFLOKSASIN может вызывать у вас головокружение или ощущение дурноты, внезапную временную потерю зрения или кратковременную потерю сознания. Если это происходит, не управляйте транспортными средствами и не работайте с механизмами во время лечения TURKTIPSAN MOKSIFLOKSASIN. |
| 21 | TURKTIPSAN MOKSİFLOKSASİN'in içeriğinde bulunan yardımcı maddeler hakkında önemli bilgiler | Важная информация о некоторых вспомогательных веществах в составе TURKTIPSAN MOKSIFLOKSASIN |
| 22 | Bir TURKTIPSAN MOKSİFLOKSASİN torbası (250 ml), 787 mg (yaklaşık 34 mmol) sodyum içermektedir. Bu durum kontrollü sodyum diyetinde olan hastalar için göz önünde bulundurulmalıdır. | Один пакет TURKTIPSAN MOKSIFLOKSASIN (250 мл) содержит 787 мг (около 34 ммоль) натрия. Это следует учитывать пациентам, соблюдающим диету с контролем натрия. |
| 23 | Eğer TURKTIPSAN MOKSİFLOKSASİN'in yanı sıra son zamanlarda başka ilaçlar kullanıyorsanız doktorunuza veya eczacınıza söyleyiniz. | Если вы недавно принимали другие препараты помимо TURKTIPSAN MOKSIFLOKSASIN, сообщите об этом врачу или фармацевту. |
| 24 | TURKTIPSAN MOKSİFLOKSASİN ve kalbinizi etkileyecek diğer ilaçları kullanıyorsanız kalp ritim hızınız için artış riski mevcuttur. Bu nedenle TURKTIPSAN MOKSİFLOKSASİN'i aşağıdaki ilaçlarla birlikte kullanmayınız: | Если вы применяете TURKTIPSAN MOKSIFLOKSASIN вместе с другими препаратами, влияющими на сердце, возникает риск нарушения сердечного ритма. Поэтому не применяйте TURKTIPSAN MOKSIFLOKSASIN вместе со следующими препаратами: |
| 25 | Kan potasyum seviyenizi azaltmak veya kalp ritim hızınızı düşürmek için başka bir ilaç alıyorsanız doktorunuza söyleyiniz (örneğin; bazı diüretikler, bazı laksatifler ve enemalar [yüksek dozlar] veya kortikosteroidler [anti-enflamatuar ilaçlar], amfoterisin B) çünkü TURKTIPSAN MOKSİFLOKSASİN kullanımı sırasında ciddi kalp ritim bozukluğu riski artışı görülebilir. | Сообщите врачу, если вы принимаете другие препараты, которые снижают уровень калия в крови или замедляют сердечный ритм (например, некоторые мочегонные, некоторые слабительные и клизмы [в высоких дозах] или кортикостероиды [противовоспалительные препараты], амфотерицин B): при применении TURKTIPSAN MOKSIFLOKSASIN может повышаться риск серьёзных нарушений сердечного ритма. |

## ULTRAVIST 300 (логи 31259, 31260)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 123 | Bu tür riskleri olan bir hastada iyot içeren kontrast madde kullanılması planlanıyorsa, ULTRAVIST verilmeden önce hastanın tiroid fonksiyonları mutlaka incelenmeli ve gerekirse tirostatik tedavi başlatılmalıdır.. | Если у пациента с такими рисками планируется применение йодсодержащего контрастного вещества, перед введением ULTRAVIST необходимо обязательно проверить функцию щитовидной железы и при необходимости начать тиреостатическую терапию. |
| 124 | Kan damarlarınızı incelemek amacıyla size ULTRAVIST enjekte edilirse ve ciddi bir dolaşım hastalığınız veya koroner damarlarınızda ciddi bir hastalık (miyokard kasında oksijen yetersizliği, göğüs ağrısı) varsa, kan dolaşımında klinik açıdan önemli değişiklikler (hemodinamik değişiklikler) ve düzensiz kalp atışı (aritmi) gelişmesi riski daha yüksek olacaktır. (Ayrıca bkz. Bölüm 3 "ULTRAVIST nasıl kullanılır?-Böbrek yetmezliği").. | Если ULTRAVIST вводят вам для исследования кровеносных сосудов и у вас есть серьёзное заболевание системы кровообращения или коронарных сосудов (недостаток кислорода в сердечной мышце, боль в груди), риск клинически значимых изменений кровообращения (гемодинамических изменений) и нерегулярного сердцебиения (аритмии) будет выше. (См. также раздел 3 «Как применяется ULTRAVIST? — Почечная недостаточность».) |
| 125 | Kalp reaksiyonları açısından özellikle risk altında olan hastalar kalp kasında zayıflık (kalp yetmezliği), ciddi koroner kalp hastalığı, kararsız anjina pektoris, kalp kapak hastalığı, yakın zamanda geçirilmiş miyokard enfarktüsü (kalp krizi), koroner baypas ve yüksek akciğer basıncı (pulmoner hipertansiyon) olan hastalardır. Kalp yetmezliğiniz varsa, ULTRAVIST uygulaması akciğerlerde sıvı birikmesine (pulmoner ödem) neden olabilir. | Особому риску сердечных реакций подвержены пациенты со слабостью сердечной мышцы (сердечной недостаточностью), тяжёлой ишемической болезнью сердца, нестабильной стенокардией, пороками клапанов сердца, недавно перенесённым инфарктом миокарда (сердечным приступом), коронарным шунтированием и высоким давлением в лёгких (лёгочной гипертензией). Если у вас сердечная недостаточность, введение ULTRAVIST может вызвать скопление жидкости в лёгких (отёк лёгких). |
| 126 | Akut pankreas iltihabı (pankreatit) ve akut safra kanalı iltihabı (kolanjit) olan hastalara safra ve pankreas kanalının endoskopik incelemesi (ERKP; endoskopik retrograd kolanjiyopankreatografi) için ULTRAVIST kullanılmadan önce dikkatli bir risk-yarar değerlendirmesi yapılmalıdır. Tıkanma yapan bir taşın çıkarılması (safra kanalında taşa bağlı tıkanma) veya daralmayı ortadan kaldırıcı baypas gibi acil tedavi girişimleri gerekmedikçe, inceleme akut belirtiler geçene kadar (3-4 hafta) ertelenmelidir. | У пациентов с острым воспалением поджелудочной железы (панкреатитом) и острым воспалением желчных протоков (холангитом) перед применением ULTRAVIST для эндоскопического исследования желчных и панкреатических протоков (ЭРХПГ — эндоскопической ретроградной холангиопанкреатографии) необходимо тщательно оценить соотношение риска и пользы. Если не требуются срочные вмешательства, такие как удаление закупоривающего камня (закупорка желчного протока камнем) или шунтирование для устранения сужения, исследование следует отложить до исчезновения острых симптомов (3–4 недели). |

## ULTRAVIST 370 (логи 31251, 31254, 31258, 31259, 31260)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 127 | Olası geçimsizlik riskinin azaltmak için, doktorunuz/eğitimli sağlık mesleği mensubu ULTRAVIST'i başka hiçbir ilaçla karıştırmayacaktır. | Чтобы снизить риск возможной несовместимости, врач или обученный медицинский работник не будет смешивать ULTRAVIST ни с какими другими препаратами. |
| 128 | ULTRAVIST'i aşağıdaki durumlarda DİKKATLİ KULLANINIZ | ULTRAVIST следует ПРИМЕНЯТЬ С ОСТОРОЖНОСТЬЮ в следующих случаях |
| 129 | Tekrarlayan ve/veya yüksek dozlarda ULTRAVIST gibi bir kontrast madde aldıysanız, | Если вы получали контрастное вещество, такое как ULTRAVIST, повторно и/или в высоких дозах, |
| 130 | bu durum ULTRAVIST'e karşı alerji benzeri bir reaksiyon (ciddi reaksiyonlar dahil) gelişme riskinizin yüksek olduğu anlamına gelir. Doktorunuz, planlanan incelemenin yapılıp yapılmayacağına karar verecektir. | это означает, что у вас повышен риск аллергоподобной реакции на ULTRAVIST (включая тяжёлые реакции). Врач решит, проводить ли запланированное исследование. |
| 131 | ULTRAVIST kullandıktan sonra, doza bağlı olarak farklı şiddette alerji benzeri (allergoid) reaksiyonlar, hatta şok veya kardiyovasküler (kalp ve kan damarlarıyla ilgili), solunum (hava yolları) ile ilgili ve kutanöz (deriyle ilgili) reaksiyonlar gibi çeşitli başka belirtiler de ortaya çıkabilir. | После применения ULTRAVIST в зависимости от дозы могут возникнуть аллергоподобные (аллергоидные) реакции разной тяжести, вплоть до шока, а также различные другие симптомы, например реакции со стороны сердечно-сосудистой системы (сердца и сосудов), дыхательных путей и кожи. |
| 132 | ULTRAVIST aldıktan sonra doktorunuz sizi en az yarım saat süreyle yakından izleyecektir. | После введения ULTRAVIST врач будет внимательно наблюдать за вами не менее получаса. |
| 133 | Aşağıdaki durumlarda ULTRAVIST kullanılırken dikkatli olunmalıdır: | ULTRAVIST следует применять с осторожностью в следующих случаях: |
| 134 | ULTRAVIST kullanımıyla ilişkili olarak Stevens-Johnson sendromu (SJS), toksik epidermal nekroliz (TEN), eozinofili ve sistemik semptomlarla birlikte seyreden ilaç reaksiyonu (DRESS) ve akut jeneralize ekzantematöz püstüloz (AGEP) dahil ciddi deri reaksiyonları bildirilmiştir."Bölüm 4 "Olası yan etkiler nelerdir?" Bölümünde açıklanan belirtilerden herhangi birini fark ettiğiniz takdirde, derhal tıbbi yardım alın. | В связи с применением ULTRAVIST сообщалось о серьёзных кожных реакциях, включая синдром Стивенса — Джонсона (ССД), токсический эпидермальный некролиз (ТЭН), лекарственную реакцию с эозинофилией и системными симптомами (DRESS) и острый генерализованный экзантематозный пустулёз (ОГЭП). Если вы заметите любой из симптомов, описанных в разделе 4 «Возможные побочные эффекты», немедленно обратитесь за медицинской помощью. |
| 135 | Bu tür riskleri olan bir hastada iyot içeren kontrast madde kullanılması planlanıyorsa, ULTRAVIST verilmeden önce hastanın tiroid fonksiyonları mutlaka incelenmeli ve gerekirse tirostatik tedavi başlatılmalıdır. | Если у пациента с такими рисками планируется применение йодсодержащего контрастного вещества, перед введением ULTRAVIST необходимо обязательно проверить функцию щитовидной железы и при необходимости начать тиреостатическую терапию. |
| 136 | Belirli durumlarda tedavi edilmesi gereken hipotiroidi riski nedeniyle doktor, özellikle erken doğan bebekler olmak üzere, hamilelik sırasında ya da doğumdan hemen sonra anne aracılığıyla ULTRAVIST'e maruz kalan yeni doğmuş bebeklerin tiroid fonksiyonlarını izleyecektir.. | Из-за риска гипотиреоза, который в некоторых случаях требует лечения, врач будет контролировать функцию щитовидной железы у новорождённых, особенно недоношенных, которые подверглись воздействию ULTRAVIST через мать во время беременности или сразу после родов. |
| 137 | Nöbet geçirme gibi herhangi bir MSS bozukluğunuz (merkezi sinir sistemi bozuklukları) varsa, doktorunuzu bilgilendiriniz. ULTRAVIST kullandığınız için nörolojik komplikasyon gelişme riskiniz daha yüksek olabilir. Bu etkiler serebral anjiyografiler (beyindeki kan damarlarının X ışını kullanılarak incelenmesi) ve diğer benzer tetkikler sırasında daha sık görülür. | Если у вас есть какое-либо нарушение ЦНС (центральной нервной системы), например судорожные припадки, сообщите врачу. Из-за применения ULTRAVIST риск неврологических осложнений у вас может быть выше. Такие эффекты чаще возникают при церебральной ангиографии (рентгенологическом исследовании сосудов головного мозга) и других подобных исследованиях. |
| 138 | Susuz kaldıysanız (vücudunuzda yeterli sıvı yoksa) size ULTRAVIST verilmemelidir. Bunu önlemek için, doktorunuz inceleme yapılmadan önce yeterince sıvı tükettiğinizden emin olacaktır (ayrıca bkz. Bölüm 2 "İntravasküler uygulamalar (kan damarı içine uygulama)"). | Если у вас обезвоживание (в организме недостаточно жидкости), ULTRAVIST вводить нельзя. Чтобы этого избежать, врач перед исследованием убедится, что вы выпили достаточно жидкости (см. также раздел 2 «Внутрисосудистое применение (введение в кровеносный сосуд)»). |
| 139 | Huzursuzluğunuz varsa, ULTRAVIST uygulamasından önce doktorunuzu bilgilendiriniz. Aşırı heyecan, huzursuzluk ve ağrı yan etki riskini artırabilir veya kontrast maddeye bağlı reaksiyonları şiddetlendirebilir (ayrıca bkz. Bölüm 4 "Olası yan etkiler"). | Если вы испытываете беспокойство, сообщите врачу перед введением ULTRAVIST. Сильное волнение, беспокойство и боль могут повышать риск побочных эффектов или усиливать реакции на контрастное вещество (см. также раздел 4 «Возможные побочные эффекты»). |
| 140 | Öngörü değeri olmaması, hatta zaman zaman ciddi veya ölümcül aşırı duyarlılık reaksiyonlarına yol açması nedeniyle, aşırı duyarlılık için düşük bir test dozunda olsa dahi ULTRAVIST kullanılarak ön test yapılması önerilmez. | Проводить предварительную пробу на повышенную чувствительность с ULTRAVIST, даже в низкой тестовой дозе, не рекомендуется: она не имеет прогностической ценности и иногда сама приводит к тяжёлым или смертельным реакциям повышенной чувствительности. |
| 141 | Kan damarlarınızı incelemek amacıyla size ULTRAVIST enjekte edilirse ve ciddi bir dolaşım hastalığınız veya koroner damarlarınızda ciddi bir hastalık (miyokard kasında oksijen yetersizliği, göğüs ağrısı) varsa, kan dolaşımında klinik açıdan önemli değişiklikler (hemodinamik değişiklikler) ve düzensiz kalp atışı (aritmi) gelişmesi riski daha yüksek olacaktır. (Ayrıca bkz. Bölüm 3 "ULTRAVIST nasıl kullanılır?-Böbrek yetmezliği"). | Если ULTRAVIST вводят вам для исследования кровеносных сосудов и у вас есть серьёзное заболевание системы кровообращения или коронарных сосудов (недостаток кислорода в сердечной мышце, боль в груди), риск клинически значимых изменений кровообращения (гемодинамических изменений) и нерегулярного сердцебиения (аритмии) будет выше. (См. также раздел 3 «Как применяется ULTRAVIST? — Почечная недостаточность».) |
| 142 | Kalp reaksiyonları açısından özellikle risk altında olan hastalar kalp kasında zayıflık (kalp yetmezliği), ciddi koroner kalp hastalığı, kararsız anjina pektoris, kalp kapak hastalığı, yakın zamanda geçirilmiş miyokard enfarktüsü (kalp krizi), koroner baypas ve yüksek akciğer basıncı (pulmoner hipertansiyon) olan hastalardır. Kalp yetmezliğiniz varsa, ULTRAVIST uygulaması akciğerlerde sıvı birikmesine (pulmoner ödeme) neden olabilir. | Особому риску сердечных реакций подвержены пациенты со слабостью сердечной мышцы (сердечной недостаточностью), тяжёлой ишемической болезнью сердца, нестабильной стенокардией, пороками клапанов сердца, недавно перенесённым инфарктом миокарда (сердечным приступом), коронарным шунтированием и высоким давлением в лёгких (лёгочной гипертензией). Если у вас сердечная недостаточность, введение ULTRAVIST может вызвать скопление жидкости в лёгких (отёк лёгких). |
| 143 | ULTRAVIST'in intravasküler (damar içine) uygulanmasını takiben böbrek hasarı (kontrast madde ile ilişkili akut böbrek hasarı/PC-AKI) riski vardır. Bu durum böbrek fonksiyonlarının geçici olarak bozulmasına yol açabilir. Bazı hastalarda böbrek yetmezliği oluşabilir. | После внутрисосудистого введения ULTRAVIST существует риск повреждения почек (острого повреждения почек, связанного с контрастным веществом, PC-AKI). Это может привести к временному нарушению функции почек. У некоторых пациентов может развиться почечная недостаточность. |
| 144 | yüksek dozda kontrast madde ve/veya çok sayıda ULTRAVIST | высокие дозы контрастного вещества и/или многократное введение ULTRAVIST |
| 145 | Böbrekleri artık düzgün çalışmayan ve diyalize ihtiyaç duyan hastalarda, iyot içeren kontrast maddeler diyaliz yoluyla atılabildiğinden, radyolojik tetkikler için ULTRAVIST verilebilir. Hemodiyaliz, radyolojik incelemeden hemen sonra yapılmalıdır. | Пациентам, у которых почки больше не работают нормально и которым нужен диализ, ULTRAVIST можно вводить для рентгенологических исследований, так как йодсодержащие контрастные вещества выводятся при диализе. Гемодиализ следует провести сразу после рентгенологического исследования. |
| 146 | ULTRAVIST'in yiyecek ve içecek ile kullanılması | Применение ULTRAVIST с пищей и напитками |
| 147 | Hamile kadınlarda iyi kontrollü çalışmalar yapılmamıştır. Bu nedenle, insanlarda hamilelik sırasında ULTRAVIST kullanımının güvenliliği yeterince kanıtlanmamıştır. İopromid ile yapılan hayvan çalışmaları, insanlarda tanı amaçlı iopromid kullanımından sonra embriyo/fetus gelişimi, doğum veya yenidoğanların gelişimi ile ilgili olarak hamilelik sırasında zararlı bir etki olduğuna dair herhangi bir kanıt göstermemiştir. | Хорошо контролируемых исследований у беременных женщин не проводилось. Поэтому безопасность применения ULTRAVIST во время беременности у человека достаточно не доказана. Исследования йопромида на животных не выявили признаков вредного влияния во время беременности на развитие эмбриона/плода, роды или развитие новорождённых после диагностического применения йопромида у человека. |
| 148 | 5. ULTRAVIST'İN SAKLANMASI | 5. ХРАНЕНИЕ ULTRAVIST |
| 149 | ULTRAVIST'i çocukların göremeyeceği, erişemeyeceği yerlerde ve ambalajında saklayınız. | Храните ULTRAVIST в недоступном и невидимом для детей месте, в упаковке. |
| 150 | Kutudaki veya şişedeki son kullanma tarihinden sonra ULTRAVIST'i kullanmayınız. | Не применяйте ULTRAVIST после истечения срока годности, указанного на коробке или флаконе. |
| 151 | Eğer üründe ve/veya ambalajında bozukluklar fark ederseniz ULTRAVIST'i kullanmayınız. Son kullanma tarihi geçmiş veya kullanılmayan ilaçları çöpe atmayınız! Çevre, Şehircilik ve | Не применяйте ULTRAVIST, если заметили повреждения продукта и/или упаковки. Не выбрасывайте просроченные или неиспользованные лекарства в мусор! Министерство окружающей среды, градостроительства и |
| 152 | Size olması gerekenden daha fazla ULTRAVIST verilirse ve kendinizi iyi hissetmediğinizi fark ederseniz derhal doktorunuza haber verin. | Если вам ввели больше ULTRAVIST, чем следует, и вы чувствуете себя плохо, немедленно сообщите врачу. |

## WARFMADIN (логи 31265, 31266, 31267, 31268, 31269, 31270, 31271)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 153 | Sinir sistemi hastalıklarında kullanılan ilaçlar: Desvenlafaksin, duloksetin, venlafaksin, sitalopram, essitalopram, fluoksetin, fluvoksamin, paroksetin, sertralin, viloksazin, tradozon, valproik asit, valproat, fosfenitoin, fenitoin, entakapon, tolkapon, ropinirol, ginkgo biloba, memantin, metilfenidat, kloral hidrat, glutetimid | Препараты, применяемые при заболеваниях нервной системы: десвенлафаксин, дулоксетин, венлафаксин, циталопрам, эсциталопрам, флуоксетин, флувоксамин, пароксетин, сертралин, вилоксазин, тразодон, вальпроевая кислота, вальпроат, фосфенитоин, фенитоин, энтакапон, толкапон, ропинирол, гинкго билоба, мемантин, метилфенидат, хлоралгидрат, глутетимид |
| 154 | Solunum sistemi hastalıklarında kullanılan ilaçlar: Zafirlukast, noskapin, oksolamin | Препараты, применяемые при заболеваниях дыхательной системы: зафирлукаст, носкапин, оксоламин |
| 155 | Hormon sistemi hastalıklarında kullanılan ilaçlar: Deksametazon, metilprednizolon, prednizon, tibolon, tamoksifen, toremifen, medroksiprogesteron, megestrol, testosteron, bikalutamid, flutamid, nilutamid, danazol, metandienon, oksandrolen, oksimetolon, stanozolol, eksenatid, glukagon, levotiroksin, liotironin, tiroid hormonu, metimazol, propiltiourasil | Препараты, применяемые при заболеваниях эндокринной системы: дексаметазон, метилпреднизолон, преднизон, тиболон, тамоксифен, торемифен, медроксипрогестерон, мегестрол, тестостерон, бикалутамид, флутамид, нилутамид, даназол, метандиенон, оксандролон, оксиметолон, станозолол, эксенатид, глюкагон, левотироксин, лиотиронин, гормон щитовидной железы, метимазол, пропилтиоурацил |
| 156 | Üreme sistemi ve böbrek hastalıklarında kullanılan ilaçlar: Tolterodin, tamsulosin | Препараты, применяемые при заболеваниях репродуктивной системы и почек: толтеродин, тамсулозин |
| 157 | Bağışıklık sistemi hastalıklarında kullanılan ilaçlar: Leflunomid | Препараты, применяемые при заболеваниях иммунной системы: лефлуномид |
| 158 | Enfeksiyon tedavisinde kullanılan antibiyotikler: Amoksisilin, benzilpenisilin, penisilin G, piperasilin, tikarsilin, sefaklor, sefamandol, sefazolin, sefiksim, sefotetan, sefonisid, sefotiam, sefoksitin, seftriakson, sefuroksim, doksisiklin, tetrasiklin, tigesiklin, azitromisin, klaritromisin, eritromisin, roksitromisin, telitromisin, neomisin, siprofloksasin, levofloksasin, nalidiksik asit, moksifloksasin, norfloksasin, pefloksasin, ofloksasin, sulfadoksin, sulfafurazol, sulfametizol, sulfametoksazol/trimetoprim, sulfisoksazol, aminosalisilik asit, izoniazid, kloramfenikol, vankomisin | Антибиотики для лечения инфекций: амоксициллин, бензилпенициллин, пенициллин G, пиперациллин, тикарциллин, цефаклор, цефамандол, цефазолин, цефиксим, цефотетан, цефоницид, цефотиам, цефокситин, цефтриаксон, цефуроксим, доксициклин, тетрациклин, тигециклин, азитромицин, кларитромицин, эритромицин, рокситромицин, телитромицин, неомицин, ципрофлоксацин, левофлоксацин, налидиксовая кислота, моксифлоксацин, норфлоксацин, пефлоксацин, офлоксацин, сульфадоксин, сульфафуразол, сульфаметизол, сульфаметоксазол/триметоприм, сульфисоксазол, аминосалициловая кислота, изониазид, хлорамфеникол, ванкомицин |
| 159 | Mantar enfeksiyonlarının tedavisinde kullanılan ilaçlar: Mikonazol, ekonazol, flukonazol, ketokonazol, itrakonazol, vorikonazol | Препараты для лечения грибковых инфекций: миконазол, эконазол, флуконазол, кетоконазол, итраконазол, вориконазол |
| 160 | Parazit enfeksiyonlarının tedavisinde kullanılan ilaçlar: Proguanil, metronidazol, nimorazol, tinidazol, kinidin | Препараты для лечения паразитарных инфекций: прогуанил, метронидазол, ниморазол, тинидазол, хинидин |
| 161 | Viral enfeksiyonların tedavisinde kullanılan ilaçlar: Delavirdin, efavirenz, etravirin, nevirapin, atazanavir, ritonavir | Препараты для лечения вирусных инфекций: делавирдин, эфавиренз, этравирин, невирапин, атазанавир, ритонавир |
| 162 | İnflamasyon ve ağrı için kullanılan ilaçlar: Asetominofen (parasetamol), aspirin (asetilsalisilik asit), diflunizal, proproksifen, tramadol, diklofenak, indometazin, ketorolak, sulindak, fenoprofen, ibuprofen, ketoprofen, naproksen, oksaprozin, selekoksib, etorikoksib, lumirakoksib, rofekoksib, mefenamik asit, meklofenamik asit, lornoksikam, piroksikam, glukozamin | Препараты, применяемые при воспалении и боли: ацетаминофен (парацетамол), аспирин (ацетилсалициловая кислота), дифлунизал, пропоксифен, трамадол, диклофенак, индометацин, кеторолак, сулиндак, фенопрофен, ибупрофен, кетопрофен, напроксен, оксапрозин, целекоксиб, эторикоксиб, лумиракоксиб, рофекоксиб, мефенамовая кислота, меклофенамовая кислота, лорноксикам, пироксикам, глюкозамин |

## WARSU (логи 31267)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 163 | Parazit enfeksiyonlarının tedavisinde kullanılan ilaçlar: Proguanil, metronidazol, nimorazol,tinidazol, kinidin | Препараты для лечения паразитарных инфекций: прогуанил, метронидазол, ниморазол, тинидазол, хинидин |

## WIN RHO SDF (логи 31398)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 164 | SDF tedavisinin muhtemel faydalarını aşırı duyarlılık reaksiyonları için potansiyele karşı tartıp değerlendirilmelidir. Ig-A noksan bireyler, Ig-A içeren kan bileşenlerinin uygulanması sonrasında, Ig-A antikorları ve anafilaktik (aniden gelişen) reaksiyonlar geliştirme potansiyeline sahiptirler. | Возможную пользу лечения SDF следует соотносить с вероятностью реакций повышенной чувствительности. У людей с дефицитом IgA после введения компонентов крови, содержащих IgA, могут образоваться антитела к IgA и развиться анафилактические (внезапные) реакции. |
| 165 | WINRHO SDF enjeksiyonundan sonra | После инъекции WINRHO SDF |
| 166 | WINRHO SDF'nin yiyecek ve içecekle kullanılması | Применение WINRHO SDF с пищей и напитками |
| 167 | Mevcut verilere göre WINRHO SDF'nin gebe kadınlarda Rh immünizasyonunun önlenmesinde kullanımı, bebekte hasar oluşturmaz. | По имеющимся данным, применение WINRHO SDF у беременных женщин для предотвращения резус-иммунизации не причиняет вреда ребёнку. |
| 168 | WINRHO SDF gebelikte ITP tedavisi için önerilmez. WINRHO SDF gebe kadınlarda risk/yarar değerlendirmesi bazında, açık olarak gerekliyse kullanılmalıdır. | WINRHO SDF не рекомендуется для лечения ИТП во время беременности. У беременных женщин WINRHO SDF следует применять только при явной необходимости, на основании оценки соотношения риска и пользы. |

## YASMIN PLUS (логи 31297)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 170 | Serviks kanseri için en önemli risk faktörü inatçı İnsan Papilloma Virüs (HPV) enfeksiyonudur. Bazı çalışmalar ilacın uzun süreli kullanımının kadınlarda serviks kanseri oluşma riskini artırdığını göstermektedir. Ancak cinsel davranışın veya İnsan Papilloma Virüsü (HPV) gibi diğer faktörlerin hangi boyutta riski artırdığı açık değildir. | Важнейший фактор риска рака шейки матки — стойкая инфекция вируса папилломы человека (ВПЧ). Некоторые исследования показывают, что длительный приём препарата повышает риск развития рака шейки матки у женщин. Однако неясно, в какой степени риск повышают сексуальное поведение или другие факторы, например вирус папилломы человека (ВПЧ). |

## ZADITEN (логи 31446)

| # | Турецкий абзац | Перевод |
|---|---|---|
| 171 | Doktorunuz tedaviye verdiğiniz yanıta göre daha yüksek ya da düşük bir doz önerebilir.6 ay ve 3 yaş arası çocuklarda | Врач может рекомендовать более высокую или более низкую дозу в зависимости от того, как вы отвечаете на лечение. Дети от 6 месяцев до 3 лет |
