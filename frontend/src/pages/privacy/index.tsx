import Head from 'next/head'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { GetServerSideProps } from 'next'
import axios from 'axios'
import { getInternalApiUrl } from '../../lib/urls'
import { Lock, FileText, Database, Shield, Cookie } from 'lucide-react'
import { SITE_NAME, SITE_URL } from '../../lib/siteMeta'

export default function PrivacyPage({ pageData }: { pageData: any }) {
    const { t } = useTranslation('common')

    return (
        <>
            <Head>
                <title>{pageData?.title || t('privacy_title', 'Политика конфиденциальности')} — {SITE_NAME}</title>
                {pageData?.meta_description && <meta name="description" content={pageData.meta_description} />}
                <meta property="og:title" content={pageData?.meta_title || pageData?.title || t('privacy_title', 'Политика конфиденциальности')} />
                {pageData?.meta_description && <meta property="og:description" content={pageData.meta_description} />}
                <meta property="og:type" content="website" />
                <meta property="og:url" content={`${SITE_URL}/privacy`} />
                {pageData?.og_image && <meta property="og:image" content={pageData.og_image} />}
            </Head>
            <main className="mx-auto max-w-5xl p-6 sm:p-10 min-h-screen">
                <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-8 shadow-sm">
                    {/* Анимированный заголовок с иконкой */}
                    <div className="text-center mb-8">
                        <div className="inline-flex h-16 w-16 mb-4 items-center justify-center rounded-2xl bg-indigo-100 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400 rotate-12 hover:rotate-0 transition-transform duration-500 hover:scale-110">
                            <Shield className="h-8 w-8" />
                        </div>
                        <h1 className="text-3xl font-bold text-main md:text-5xl mb-4">
                            {pageData?.title || t('privacy_title', 'Политика конфиденциальности')}
                        </h1>
                    </div>

                    {/* Если в админке есть текст (контент), выводим его здесь */}
                    {pageData?.content ? (
                        <div
                            className="prose prose-indigo max-w-none text-main/80 mb-12"
                            dangerouslySetInnerHTML={{ __html: pageData.content }}
                        />
                    ) : (
                        <p className="mb-12 text-lg text-main/80 text-center max-w-2xl mx-auto">
                            {t('privacy_subtitle', 'Узнайте больше о том, как мы бережем и обрабатываем ваши данные. Ваш покой — наш приоритет.')}
                        </p>
                    )}

                    {/* Разделитель */}
                    <div className="h-px w-full bg-gradient-to-r from-transparent via-gray-200 to-transparent dark:via-gray-700 mb-12"></div>

                    {/* Анимированные информационные карточки */}
                    <h2 className="text-2xl font-bold text-main mb-6 text-center">{t('privacy_features', 'Наш подход к безопасности')}</h2>
                    <div className="grid gap-6 md:grid-cols-3 mb-12">
                        {/* Карточка 1 */}
                        <div className="relative group rounded-xl bg-gradient-to-br from-indigo-50 to-white border border-indigo-100 p-6 shadow-sm hover:shadow-md transition-all duration-300 dark:from-indigo-950/20 dark:to-gray-900 dark:border-indigo-900/40">
                            <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-100 text-indigo-600 dark:bg-indigo-900/60 dark:text-indigo-400 group-hover:scale-105 transition-transform duration-300">
                                <Lock className="h-6 w-6" />
                            </div>
                            <h3 className="text-lg font-bold text-main mb-2">
                                {t('privacy_secure', 'Полная защита')}
                            </h3>
                            <p className="text-sm text-main/70">
                                {t('privacy_secure_desc', 'Все данные, передаваемые между вашим браузером и нашим сервером, шифруются по протоколу SSL. Мы не передаем вашу информацию третьим лицам без вашего согласия.')}
                            </p>
                        </div>

                        {/* Карточка 2 */}
                        <div className="relative group rounded-xl bg-gradient-to-br from-pink-50 to-white border border-pink-100 p-6 shadow-sm hover:shadow-md transition-all duration-300 dark:from-pink-950/20 dark:to-gray-900 dark:border-pink-900/40">
                            <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-pink-100 text-pink-600 dark:bg-pink-900/60 dark:text-pink-400 group-hover:scale-105 transition-transform duration-300">
                                <Database className="h-6 w-6" />
                            </div>
                            <h3 className="text-lg font-bold text-main mb-2">
                                {t('privacy_data', 'Сбор данных')}
                            </h3>
                            <p className="text-sm text-main/70">
                                {t('privacy_data_desc', 'Мы собираем только ту информацию, которая необходима для обработки вашего заказа: контакты, адрес доставки и данные профиля.')}
                            </p>
                        </div>

                        {/* Карточка 3 */}
                        <div className="relative group rounded-xl bg-gradient-to-br from-purple-50 to-white border border-purple-100 p-6 shadow-sm hover:shadow-md transition-all duration-300 dark:from-purple-950/20 dark:to-gray-900 dark:border-purple-900/40">
                            <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-purple-100 text-purple-600 dark:bg-purple-900/60 dark:text-purple-400 group-hover:scale-105 transition-transform duration-300">
                                <FileText className="h-6 w-6" />
                            </div>
                            <h3 className="text-lg font-bold text-main mb-2">
                                {t('privacy_info', 'Ваши права')}
                            </h3>
                            <p className="text-sm text-main/70">
                                {t('privacy_info_desc', 'Вы можете в любой момент запросить удаление ваших данных, а также отказаться от рассылок в настройках личного кабинета.')}
                            </p>
                        </div>
                    </div>

                    {/* ── Секция Cookie ────────────────────────────────── */}
                    <div className="h-px w-full bg-gradient-to-r from-transparent via-gray-200 to-transparent dark:via-gray-700 mb-10"></div>

                    <div id="cookies" className="scroll-mt-20">
                        <div className="flex items-center gap-3 mb-6">
                            <div className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400">
                                <Cookie className="h-5 w-5" />
                            </div>
                            <h2 className="text-2xl font-bold text-main">
                                {t('privacy_cookies_title', 'Использование файлов cookie')}
                            </h2>
                        </div>

                        <p className="text-main/75 mb-6 leading-relaxed">
                            {t('privacy_cookies_desc', 'Наш сайт использует файлы cookie — небольшие текстовые файлы, которые сохраняются на вашем устройстве. Мы разделяем их на два типа:')}
                        </p>

                        <div className="grid gap-4 md:grid-cols-2 mb-6">
                            {/* Необходимые */}
                            <div className="rounded-xl border border-green-100 bg-green-50/50 p-5 dark:bg-green-900/10 dark:border-green-900/30">
                                <div className="flex items-center gap-2 mb-3">
                                    <span className="inline-block w-2.5 h-2.5 rounded-full bg-green-500"></span>
                                    <h3 className="font-semibold text-main">
                                        {t('privacy_cookies_necessary', 'Необходимые cookie')}
                                    </h3>
                                </div>
                                <p className="text-sm text-main/70 leading-relaxed">
                                    {t('privacy_cookies_necessary_desc', 'Технически обязательные файлы: корзина покупок, сессия входа, языковые настройки. Устанавливаются автоматически и не требуют согласия.')}
                                </p>
                            </div>

                            {/* Аналитические */}
                            <div className="rounded-xl border border-blue-100 bg-blue-50/50 p-5 dark:bg-blue-900/10 dark:border-blue-900/30">
                                <div className="flex items-center gap-2 mb-3">
                                    <span className="inline-block w-2.5 h-2.5 rounded-full bg-blue-500"></span>
                                    <h3 className="font-semibold text-main">
                                        {t('privacy_cookies_analytics', 'Аналитические cookie')}
                                    </h3>
                                </div>
                                <p className="text-sm text-main/70 leading-relaxed">
                                    {t('privacy_cookies_analytics_desc', 'Google Analytics (через Google Tag Manager) и Яндекс.Метрика для анализа посещаемости сайта. Устанавливаются только с вашего явного согласия.')}
                                </p>
                            </div>
                        </div>

                        <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-5 dark:bg-indigo-900/10 dark:border-indigo-900/30">
                            <h3 className="font-semibold text-main mb-2">
                                {t('privacy_cookies_consent', 'Управление согласием')}
                            </h3>
                            <p className="text-sm text-main/70 leading-relaxed">
                                {t('privacy_cookies_consent_desc', 'При первом посещении мы запрашиваем ваше согласие. Вы можете в любой момент отозвать согласие, очистив cookie браузера или нажав "Только необходимые" при следующем посещении.')}
                            </p>
                        </div>
                    </div>
                    {/* ── / Секция Cookie ──────────────────────────────── */}
                </div>
            </main>
        </>
    )
}


export const getServerSideProps: GetServerSideProps = async (ctx) => {
    let pageData = null
    try {
        const lang = ctx.locale || 'ru'
        const res = await axios.get(getInternalApiUrl('pages/privacy/') + `?lang=${lang}`)
        pageData = res.data
    } catch (error) {
        console.error('Failed to fetch static page: privacy')
    }

    return {
        props: {
            pageData,
            ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])),
        },
    }
}
