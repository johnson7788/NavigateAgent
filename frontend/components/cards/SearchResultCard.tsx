import React, { useState } from 'react';
import { SearchRecord } from '../../types';
import { Calendar, Users, ExternalLink, BookOpen, ChevronDown, ChevronUp } from 'lucide-react';

interface SearchResultCardProps {
  records: SearchRecord[];
  query?: string;
}

export const SearchResultCard: React.FC<SearchResultCardProps> = ({ records, query }) => {
  const [showAll, setShowAll] = useState(false);
  const visibleRecords = showAll ? records : records.slice(0, 1);
  const hasMore = records.length > 1;

  return (
    <div className="w-full mt-4 space-y-4">
      <div className="flex items-center space-x-2 text-sm text-gray-500 mb-2">
        <span className="bg-blue-100 text-blue-800 px-2 py-0.5 rounded text-xs font-medium">Search Results</span>
        {query && <span>Query: "{query}"</span>}
        <span>({records.length} results)</span>
      </div>

      <div className="grid gap-4 grid-cols-1 md:grid-cols-1 lg:grid-cols-1 xl:grid-cols-1">
        {visibleRecords.map((record, index) => (
          <div key={index} className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm hover:shadow-md transition-shadow duration-200">
            <div className="flex items-start justify-between mb-2">
              <h3 className="text-md font-semibold text-gray-900 line-clamp-2 leading-tight pr-2">
                {record.title}
              </h3>
              {record.link && (
                <a
                  href={record.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-gray-400 hover:text-blue-600 transition-colors flex-shrink-0"
                  title="View Article"
                >
                  <ExternalLink size={16} />
                </a>
              )}
            </div>

            <div className="text-xs text-gray-500 flex flex-wrap gap-y-1 gap-x-4 mb-3">
              <div className="flex items-center">
                <Users size={12} className="mr-1" />
                <span className="line-clamp-1 max-w-[200px]">{record.authors}</span>
              </div>
              {record.publish_date && (
                <div className="flex items-center">
                  <Calendar size={12} className="mr-1" />
                  <span>{new Date(record.publish_date).toLocaleDateString()}</span>
                </div>
              )}
              {record.journal && (
                <div className="flex items-center">
                  <BookOpen size={12} className="mr-1" />
                  <span className="line-clamp-1 max-w-[150px]">{record.journal}</span>
                </div>
              )}
              {record.impact_factor > 0 && (
                <div className="bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded text-xs">
                  IF: {record.impact_factor}
                </div>
              )}
            </div>

            {record.publication_type && (
              <div className="mb-3">
                <span className="bg-gray-100 text-gray-700 px-2 py-1 rounded text-xs">
                  {record.publication_type}
                </span>
              </div>
            )}

            <p className="text-sm text-gray-600 mb-4 leading-relaxed line-clamp-4">
              {record.abstract}
            </p>

            <div className="pt-3 border-t border-gray-100">
              <button
                className="text-xs font-medium text-blue-600 hover:text-blue-800 flex items-center"
                onClick={() => {
                  if (record.link) {
                    window.open(record.link, '_blank');
                  }
                }}
              >
                <ExternalLink size={12} className="mr-1" /> View Full Article
              </button>
            </div>
          </div>
        ))}
      </div>

      {hasMore && (
        <button
          onClick={() => setShowAll(!showAll)}
          className="w-full py-2 text-sm text-blue-600 hover:text-blue-800 flex items-center justify-center"
        >
          {showAll ? (
            <>
              <ChevronUp size={16} className="mr-1" /> Collapse
            </>
          ) : (
            <>
              <ChevronDown size={16} className="mr-1" /> Show {records.length - 1} more
            </>
          )}
        </button>
      )}
    </div>
  );
};