'use client';

import { SearchInterface } from '../../components/SearchInterface';

export default function SearchPage() {
  return (
    <main className="min-h-screen bg-gray-100 flex items-center justify-center p-2 md:p-4">
      <div className="w-full h-full">
        <SearchInterface />
      </div>
    </main>
  );
}