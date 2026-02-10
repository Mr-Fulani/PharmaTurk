'use client';

import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Search, Filter, Grid, List } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import ProductCard from '../components/ProductCard';
import api from '../lib/api';

interface Product {
  id: number;
  name: string;
  slug: string;
  description: string;
  price: number;
  old_price?: number;
  old_price_formatted?: string | null;
  main_image?: string;
  main_image_url?: string;
  currency: string;
  is_featured: boolean;
  is_available: boolean;
  isbn?: string | null;
  publisher?: string | null;
  pages?: number | null;
  language?: string | null;
  rating?: number | string | null;
  reviews_count?: number | null;
  is_bestseller?: boolean;
  is_new?: boolean;
  book_authors?: { id: number; author: { full_name: string } }[];
}

interface Category {
  id: number;
  name: string;
  slug: string;
  description: string;
  product_count?: number;
}

const parsePriceWithCurrency = (value?: string | number | null) => {
  if (value === null || typeof value === 'undefined') {
    return { price: null as string | number | null, currency: null as string | null };
  }
  if (typeof value === 'number') {
    return { price: value, currency: null as string | null };
  }
  const trimmed = value.trim();
  const match = trimmed.match(/^([0-9]+(?:[.,][0-9]+)?)\s*([A-Za-z]{3,5})$/);
  if (match) {
    return { price: match[1].replace(',', '.'), currency: match[2].toUpperCase() };
  }
  return { price: trimmed, currency: null as string | null };
};

const BookHavenPage: React.FC = () => {
  const { t } = useTranslation('common');
  const [books, setBooks] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [sortBy, setSortBy] = useState<string>('-created_at');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');

  useEffect(() => {
    loadCategories();
    loadBooks();
  }, []);

  useEffect(() => {
    loadBooks();
  }, [searchTerm, selectedCategory, sortBy]);

  const loadCategories = async () => {
    try {
      const response = await api.get('/catalog/categories', {
        params: { slug: 'books', include_children: true }
      });
      const allCategories = response.data.results || response.data;
      // Фильтруем только подкатегории книг (те, у которых есть parent)
      const bookSubcategories = allCategories.filter((cat: Category) => cat.id !== 226 && cat.slug !== 'books');
      setCategories(bookSubcategories);
    } catch (error) {
      console.error('Failed to load categories:', error);
    }
  };

  const loadBooks = async () => {
    try {
      setLoading(true);
      const params: any = {
        product_type: 'books',
        page_size: 100
      };
      
      if (searchTerm) params.search = searchTerm;
      if (selectedCategory) params.category_slug = selectedCategory;
      if (sortBy) params.ordering = sortBy;

      const response = await api.get('/catalog/products', { params });
      setBooks(response.data.results || []);
    } catch (error) {
      console.error('Failed to load books:', error);
      setBooks([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#fbeee0]">
      {/* Header */}
      <div className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-black">{t('books_page_title', 'Книги')}</h1>
              <p className="text-gray-600 mt-1">{t('books_page_subtitle', 'Ваша книжная гавань')}</p>
            </div>
            <div className="flex items-center gap-4">
              <button
                className={`p-2 rounded-lg transition-colors ${
                  viewMode === 'grid'
                    ? 'bg-[#ff8c42] text-white'
                    : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
                }`}
                onClick={() => setViewMode('grid')}
              >
                <Grid className="w-4 h-4" />
              </button>
              <button
                className={`p-2 rounded-lg transition-colors ${
                  viewMode === 'list'
                    ? 'bg-[#ff8c42] text-white'
                    : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
                }`}
                onClick={() => setViewMode('list')}
              >
                <List className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex flex-col sm:flex-row gap-4">
            {/* Search */}
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
              <input
                type="text"
                placeholder={t('books_search_placeholder', 'Поиск книг, авторов...')}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#ff8c42] focus:border-transparent"
              />
            </div>

            {/* Category Filter */}
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="w-full sm:w-48 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#ff8c42] focus:border-transparent bg-white"
            >
              <option value="">{t('books_all_categories', 'Все категории')}</option>
              {categories.map((category) => (
                <option key={category.id} value={category.slug}>
                  {category.name} ({category.product_count || 0})
                </option>
              ))}
            </select>

            {/* Sort */}
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="w-full sm:w-48 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#ff8c42] focus:border-transparent bg-white"
            >
              <option value="-created_at">{t('books_sort_newest', 'Новинки')}</option>
              <option value="name">{t('books_sort_name_asc', 'По названию А-Я')}</option>
              <option value="-name">{t('books_sort_name_desc', 'По названию Я-А')}</option>
              <option value="price">{t('books_sort_price_asc', 'Цена: по возрастанию')}</option>
              <option value="-price">{t('books_sort_price_desc', 'Цена: по убыванию')}</option>
              <option value="-rating">{t('books_sort_rating', 'По рейтингу')}</option>
            </select>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {loading ? (
          <div className="flex justify-center items-center h-64">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#ff8c42]"></div>
          </div>
        ) : books.length === 0 ? (
          <div className="text-center py-12">
            <h3 className="text-lg font-medium text-gray-900 mb-2">{t('books_not_found', 'Книги не найдены')}</h3>
            <p className="text-gray-500">{t('books_not_found_description', 'Попробуйте изменить параметры поиска или фильтры')}</p>
          </div>
        ) : (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5 }}
            className={
              viewMode === 'grid'
                ? 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6'
                : 'space-y-4'
            }
          >
            {books.map((book) => {
              const displayPrice = book.price ? String(book.price) : null;
              const oldPriceSource = book.old_price_formatted ?? book.old_price ?? null;
              const { price: parsedOldPrice, currency: parsedOldCurrency } = parsePriceWithCurrency(oldPriceSource);
              const displayCurrency = book.currency || 'RUB';
              const displayOldCurrency = parsedOldCurrency || displayCurrency;
              const displayOldPriceValue = displayOldCurrency === displayCurrency ? (parsedOldPrice ?? oldPriceSource) : null;
              const displayOldPrice = displayOldPriceValue ? String(displayOldPriceValue) : null;
              const ratingNum =
                book.rating != null
                  ? typeof book.rating === 'number'
                    ? book.rating
                    : Number(book.rating)
                  : undefined;
              const rating = ratingNum !== undefined && !Number.isNaN(ratingNum) ? ratingNum : undefined;

              return (
                <ProductCard
                  key={book.id}
                  id={book.id}
                  name={book.name}
                  slug={book.slug}
                  price={displayPrice}
                  currency={book.currency || 'RUB'}
                  oldPrice={displayOldPrice}
                  imageUrl={book.main_image_url || book.main_image}
                  badge={book.is_featured ? 'Хит' : null}
                  viewMode={viewMode}
                  description={book.description}
                  href={`/product/books/${book.slug}`}
                  productType="books"
                  isBaseProduct={true}
                  isbn={book.isbn}
                  publisher={book.publisher}
                  pages={book.pages}
                  language={book.language}
                  authors={book.book_authors}
                  reviewsCount={book.reviews_count}
                  isBestseller={book.is_bestseller}
                  isNew={book.is_new}
                  rating={rating}
                />
              );
            })}
          </motion.div>
        )}
      </div>
    </div>
  );
};

export default BookHavenPage;
