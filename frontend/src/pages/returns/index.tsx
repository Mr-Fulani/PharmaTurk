import Head from 'next/head'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { GetServerSideProps } from 'next'
import axios from 'axios'
import { getInternalApiUrl } from '../../lib/urls'
import { RefreshCcw, PackageCheck, HeadphonesIcon } from 'lucide-react'

export default function ReturnsPage({ pageData }: { pageData: any }) {
    const { t } = useTranslation('common')

    return (
        <>
            <Head>
                <title>{pageData?.title || t('returns_title', 'Возврат и обмен')} — Turk-Export</title>
            </Head>
            <main className="mx-auto max-w-5xl p-6 sm:p-10 min-h-screen">
                <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-8 shadow-sm">
                    {/* Заголовок */}
                    <h1 className="mb-4 text-3xl font-bold text-main md:text-4xl text-center">
                        {pageData?.title || t('returns_title', 'Возврат и обмен')}
                    </h1>

                    {/* Если в админке есть текст (контент), выводим его здесь */}
                    {pageData?.content ? (
                        <div
                            className="prose prose-red max-w-none text-main/80 mb-12"
                            dangerouslySetInnerHTML={{ __html: pageData.content }}
                        />
                    ) : (
                        <p className="mb-12 text-lg text-main/80 text-center max-w-2xl mx-auto">
                            {t('returns_subtitle', 'Условия возврата и обмена товаров. Мы гарантируем 14 дней на возврат товара надлежащего качества без объяснения причин.')}
                        </p>
                    )}

                    {/* Анимированный блок процесса возврата */}
                    <h2 className="text-2xl font-bold text-main mb-8 text-center">{t('returns_steps', 'Как оформить возврат? 3 простых шага')}</h2>

                    <div className="relative mb-16 px-4">
                        {/* Соединительная линия между шагами (скрыта на мобильных) */}
                        <div className="hidden md:block absolute top-[28px] left-[15%] right-[15%] h-0.5 bg-gradient-to-r from-red-100 via-red-300 to-red-100 dark:from-red-900/30 dark:via-red-800 dark:to-red-900/30"></div>

                        <div className="grid gap-8 md:grid-cols-3">
                            {/* Шаг 1 */}
                            <div className="relative group rounded-2xl bg-white border border-gray-100 p-6 pt-10 text-center shadow-sm hover:shadow-md hover:border-red-200 transition-all duration-300 dark:bg-gray-800/50 dark:border-gray-700/50 transform hover:-translate-y-1">
                                <div className="absolute -top-6 left-1/2 -translate-x-1/2 flex h-14 w-14 items-center justify-center rounded-full bg-white border-[3px] border-red-500 text-red-600 shadow-md group-hover:scale-110 transition-transform duration-300 dark:bg-gray-900 dark:text-red-400">
                                    <HeadphonesIcon className="h-6 w-6" />
                                </div>
                                <h3 className="text-lg font-bold text-main mb-2">
                                    {t('return_step_1_title', '1. Свяжитесь со службой поддержки')}
                                </h3>
                                <p className="text-sm text-main/70">
                                    {t('return_step_1_text', 'Напишите нам в течение 14 дней. Мы оперативно обработаем вашу заявку и согласуем процесс возврата.')}
                                </p>
                            </div>

                            {/* Шаг 2 */}
                            <div className="relative group rounded-2xl bg-white border border-gray-100 p-6 pt-10 text-center shadow-sm hover:shadow-md hover:border-red-200 transition-all duration-300 dark:bg-gray-800/50 dark:border-gray-700/50 transform hover:-translate-y-1">
                                <div className="absolute -top-6 left-1/2 -translate-x-1/2 flex h-14 w-14 items-center justify-center rounded-full bg-white border-[3px] border-red-500 text-red-600 shadow-md group-hover:scale-110 transition-transform duration-300 dark:bg-gray-900 dark:text-red-400">
                                    <PackageCheck className="h-6 w-6" />
                                </div>
                                <h3 className="text-lg font-bold text-main mb-2">
                                    {t('return_step_2_title', '2. Упакуйте и отправьте товар')}
                                </h3>
                                <p className="text-sm text-main/70">
                                    {t('return_step_2_text', 'Убедитесь, что товар сохранил свой первоначальный вид, пломбы и бирки. Отправьте посылку по указанному нами адресу.')}
                                </p>
                            </div>

                            {/* Шаг 3 */}
                            <div className="relative group rounded-2xl bg-white border border-gray-100 p-6 pt-10 text-center shadow-sm hover:shadow-md hover:border-red-200 transition-all duration-300 dark:bg-gray-800/50 dark:border-gray-700/50 transform hover:-translate-y-1">
                                <div className="absolute -top-6 left-1/2 -translate-x-1/2 flex h-14 w-14 items-center justify-center rounded-full bg-white border-[3px] border-red-500 text-red-600 shadow-md group-hover:scale-110 transition-transform duration-300 dark:bg-gray-900 dark:text-red-400">
                                    <RefreshCcw className="h-6 w-6" />
                                </div>
                                <h3 className="text-lg font-bold text-main mb-2">
                                    {t('return_step_3_title', '3. Получите возврат средств')}
                                </h3>
                                <p className="text-sm text-main/70">
                                    {t('return_step_3_text', 'После получения и проверки товара мы переведем средства или отправим вам новый товар на замену в течение 3-5 дней.')}
                                </p>
                            </div>
                        </div>
                    </div>

                    {/* Разделитель */}
                    <div className="h-px w-full bg-gradient-to-r from-transparent via-gray-200 to-transparent dark:via-gray-700 mb-12"></div>

                    {/* Блок частых вопросов (Дополнительно) */}
                    <div className="rounded-xl bg-gray-50/80 p-6 dark:bg-gray-800/40 text-center">
                        <h3 className="text-xl font-semibold text-main mb-2">{t('return_policy_note', 'Есть вопросы по возврату брака?')}</h3>
                        <p className="text-main/70 max-w-2xl mx-auto">{t('return_policy_note_desc', 'Если вы обнаружили брак, мы берем на себя все транспортные расходы и произведем обмен в максимально короткие сроки. Пожалуйста, приложите фото брака к своему обращению в поддержку.')}</p>
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
        const res = await axios.get(getInternalApiUrl('pages/returns/') + `?lang=${lang}`)
        pageData = res.data
    } catch (error) {
        console.error('Failed to fetch static page: returns')
    }

    return {
        props: {
            pageData,
            ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])),
        },
    }
}
