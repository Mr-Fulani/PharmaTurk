import Head from 'next/head'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { GetServerSideProps } from 'next'
import axios from 'axios'
import { getInternalApiUrl } from '../../lib/urls'
import { Plane, Truck, Ship, CreditCard, ShieldCheck } from 'lucide-react'

export default function DeliveryPage({ pageData }: { pageData: any }) {
    const { t } = useTranslation('common')

    return (
        <>
            <Head>
                <title>{pageData?.title || t('delivery_title', 'Доставка и оплата')} — Turk-Export</title>
            </Head>
            <main className="mx-auto max-w-5xl p-6 sm:p-10 min-h-screen">
                <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-8 shadow-sm">
                    {/* Заголовок */}
                    <h1 className="mb-4 text-3xl font-bold text-main md:text-4xl text-center">
                        {pageData?.title || t('delivery_title', 'Доставка и оплата')}
                    </h1>

                    {/* Если в админке есть текст (контент), выводим его здесь */}
                    {pageData?.content ? (
                        <div
                            className="prose prose-red max-w-none text-main/80 mb-12"
                            dangerouslySetInnerHTML={{ __html: pageData.content }}
                        />
                    ) : (
                        <p className="mb-12 text-lg text-main/80 text-center max-w-2xl mx-auto">
                            {t('delivery_subtitle', 'Информация о способах доставки и оплаты. Мы предлагаем удобные и безопасные способы получения и оплаты ваших заказов по всему миру.')}
                        </p>
                    )}

                    {/* Анимированный блок способов доставки */}
                    <h2 className="text-2xl font-bold text-main mb-6 text-center">{t('delivery_methods', 'Способы доставки')}</h2>
                    <div className="grid gap-6 md:grid-cols-3 mb-16">
                        {/* Воздушный путь */}
                        <div className="group rounded-2xl bg-white border border-gray-100 p-6 shadow-sm hover:shadow-md hover:border-red-200 transition-all duration-300 dark:bg-gray-800/50 dark:border-gray-700/50 dark:hover:border-red-900/50 transform hover:-translate-y-1 relative overflow-hidden">
                            <div className="absolute -right-4 -top-4 w-24 h-24 bg-blue-50/50 rounded-full blur-2xl group-hover:bg-blue-100 transition-colors dark:bg-blue-900/20"></div>
                            <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-xl bg-blue-50 text-blue-600 dark:bg-blue-900/40 dark:text-blue-400 group-hover:scale-110 transition-transform duration-300">
                                <Plane className="h-7 w-7" />
                            </div>
                            <h3 className="text-xl font-bold text-main mb-2">
                                {t('delivery_air', 'Воздушным путем')}
                            </h3>
                            <p className="text-sm text-main/70">
                                {t('delivery_air_desc', 'Самый быстрый способ доставки. Идеально подходит для срочных грузов и небольших посылок. Сроки: от 3 до 7 дней.')}
                            </p>
                        </div>

                        {/* Наземный путь */}
                        <div className="group rounded-2xl bg-white border border-gray-100 p-6 shadow-sm hover:shadow-md hover:border-red-200 transition-all duration-300 dark:bg-gray-800/50 dark:border-gray-700/50 dark:hover:border-red-900/50 transform hover:-translate-y-1 relative overflow-hidden">
                            <div className="absolute -right-4 -top-4 w-24 h-24 bg-green-50/50 rounded-full blur-2xl group-hover:bg-green-100 transition-colors dark:bg-green-900/20"></div>
                            <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-xl bg-green-50 text-green-600 dark:bg-green-900/40 dark:text-green-400 group-hover:scale-110 transition-transform duration-300">
                                <Truck className="h-7 w-7" />
                            </div>
                            <h3 className="text-xl font-bold text-main mb-2">
                                {t('delivery_ground', 'Наземным путем')}
                            </h3>
                            <p className="text-sm text-main/70">
                                {t('delivery_ground_desc', 'Оптимальное соотношение цены и скорости. Доставка автотранспортом. Сроки: от 7 до 14 дней в зависимости от региона.')}
                            </p>
                        </div>

                        {/* Морской путь */}
                        <div className="group rounded-2xl bg-white border border-gray-100 p-6 shadow-sm hover:shadow-md hover:border-red-200 transition-all duration-300 dark:bg-gray-800/50 dark:border-gray-700/50 dark:hover:border-red-900/50 transform hover:-translate-y-1 relative overflow-hidden">
                            <div className="absolute -right-4 -top-4 w-24 h-24 bg-cyan-50/50 rounded-full blur-2xl group-hover:bg-cyan-100 transition-colors dark:bg-cyan-900/20"></div>
                            <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-xl bg-cyan-50 text-cyan-600 dark:bg-cyan-900/40 dark:text-cyan-400 group-hover:scale-110 transition-transform duration-300 relative">
                                <Ship className="h-7 w-7 absolute" />
                                <div className="absolute bottom-1 w-8 h-1 bg-cyan-200/50 rounded-full animate-pulse blur-[1px]"></div>
                            </div>
                            <h3 className="text-xl font-bold text-main mb-2">
                                {t('delivery_sea', 'Морским путем')}
                            </h3>
                            <p className="text-sm text-main/70">
                                {t('delivery_sea_desc', 'Лучший выбор для крупногабаритных грузов и оптовых партий. Наиболее экономичный вариант. Сроки: от 20 до 45 дней.')}
                            </p>
                        </div>
                    </div>

                    {/* Разделитель */}
                    <div className="h-px w-full bg-gradient-to-r from-transparent via-gray-200 to-transparent dark:via-gray-700 mb-16"></div>

                    {/* Блок оплаты */}
                    <h2 className="text-2xl font-bold text-main mb-6 text-center">{t('payment_methods', 'Безопасная оплата')}</h2>
                    <div className="grid gap-8 md:grid-cols-2">
                        <div className="flex gap-4 items-start">
                            <div className="flex-shrink-0 mt-1 h-12 w-12 rounded-full bg-orange-100 flex items-center justify-center text-orange-600 dark:bg-orange-900/30 dark:text-orange-400">
                                <CreditCard className="w-6 h-6" />
                            </div>
                            <div>
                                <h4 className="text-lg font-bold text-main mb-1">{t('payment_cards', 'Банковские карты и переводы')}</h4>
                                <p className="text-sm text-main/70">{t('delivery_payment_text1', 'Вы можете оплатить заказ банковской картой (Visa, Mastercard, UnionPay), банковским переводом или криптовалютой напрямую.')}</p>
                            </div>
                        </div>

                        <div className="flex gap-4 items-start">
                            <div className="flex-shrink-0 mt-1 h-12 w-12 rounded-full bg-purple-100 flex items-center justify-center text-purple-600 dark:bg-purple-900/30 dark:text-purple-400">
                                <ShieldCheck className="w-6 h-6" />
                            </div>
                            <div>
                                <h4 className="text-lg font-bold text-main mb-1">{t('delivery_payment_security', '100% Защита платежей')}</h4>
                                <p className="text-sm text-main/70">{t('delivery_payment_text2', 'Все платежи надежно защищены современными 256-битными системами шифрования. Мы никогда не храним данные ваших карт на серверах.')}</p>
                            </div>
                        </div>
                    </div>

                </div>
            </main>
        </>
    )
}

export const getServerSideProps: GetServerSideProps = async (ctx) => {
    let pageData = null
    try {
        const lang = ctx.locale || 'ru'
        const res = await axios.get(getInternalApiUrl('pages/delivery/') + `?lang=${lang}`)
        pageData = res.data
    } catch (error) {
        // Если страница в админке не создана, pageData останется null
        console.error('Failed to fetch static page: delivery')
    }

    return {
        props: {
            pageData,
            ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])),
        },
    }
}
