import React from 'react';
import { useTranslation } from 'next-i18next';

interface ServiceAttribute {
    id: number;
    key: string;
    key_display: string;
    value: string;
    sort_order: number;
}

interface ServiceAttributesProps {
    attributes: ServiceAttribute[];
    title?: string;
}

const ServiceAttributes: React.FC<ServiceAttributesProps> = ({ attributes, title }) => {
    const { t } = useTranslation('common');
    if (!attributes || attributes.length === 0) return null;

    return (
        <div className="mt-8 border-t border-gray-100 dark:border-gray-800 pt-8">
            <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-6 px-1">
                {title || t('service_specifications', 'Спецификации услуги')}
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-6">
                {attributes.sort((a, b) => a.sort_order - b.sort_order).map((attr) => (
                    <div key={attr.id} className="group flex flex-col gap-2 px-1">
                        <span className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                            {t(attr.key === 'language' ? 'language_attr' : (attr.key === 'other' ? 'other_attr' : attr.key), attr.key_display)}
                        </span>
                        <div className="flex items-center gap-3">
                            <div className="h-2 w-2 rounded-full bg-blue-600 dark:bg-blue-400 opacity-80 group-hover:opacity-100 transition-opacity" />
                            <span className="text-base font-medium text-gray-900 dark:text-gray-100 leading-snug">
                                {(() => {
                                    const rawVal = (attr.value || '').trim();
                                    const isHttp = rawVal.startsWith('http://') || rawVal.startsWith('https://');
                                    const isWww = rawVal.startsWith('www.');
                                    
                                    if (isHttp || isWww) {
                                        const href = isWww ? `https://${rawVal}` : rawVal;
                                        return (
                                            <a
                                                href={href}
                                                target="_self"
                                                className="text-red-600 dark:text-red-500 font-medium hover:underline break-all"
                                            >
                                                {rawVal}
                                            </a>
                                        );
                                    }
                                    return attr.value;
                                })()}
                            </span>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default ServiceAttributes;
