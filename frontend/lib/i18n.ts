'use client'

import { useLanguage, type Language } from '@/lib/language'

const en = {
  'tab.patient': 'Patient explanation',
  'tab.doctor': 'Doctor summary',
  'tab.fields': 'Extracted data',
  'tab.compare': 'Compare',
  'doc.uploaded': 'Uploaded',
  'doc.confirmed': 'confirmed',
  'doc.openOriginal': 'Open original',
  'doc.openFailed': 'Could not open the original file.',
  'doc.viewTrends': 'View trends',
  'doc.loading': 'Loading report…',
  'doc.notFound': "This report was not found or you don't have access to it.",
  'doc.back': 'Back to dashboard',
  'doc.confirmPrompt':
    'Check the extracted values below and confirm the report. Summaries, flags and trends are generated from confirmed reports only.',
  'doc.processing': 'This report is still being processed ({status}). Summaries appear once it is confirmed.',
  'doc.awaitingPatient': 'Summaries and comparisons appear once the patient confirms this report.',
  'summary.disclaimer':
    'Informational only — not a diagnosis. Generated from the confirmed values in this report. Discuss any decision with your doctor.',
  'summary.version': 'Version',
  'summary.latest': 'Latest',
  'summary.regenerate': 'Regenerate',
  'summary.regenerating': 'Regenerating…',
  'summary.loading': 'Loading summary…',
  'summary.translating': 'Translating to Bangla… showing English until it is ready.',
  'summary.translationFailed': 'Bangla translation is unavailable right now — showing English.',
  'summary.loadFailed': 'Could not load this summary. Refresh to try again.',
  'summary.pending': 'Generating summary… this usually takes under a minute.',
  'summary.failed': 'The summary could not be generated.',
  'summary.retryHint': ' Use Regenerate to try again.',
  'summary.regenerateFailed': 'Could not start regeneration. Try again shortly.',
  'summary.meta': 'Version {version} · generated {date}',
  'summary.noneNoted': 'None noted.',
  'summary.chiefFindings': 'Chief findings',
  'summary.abnormalValues': 'Abnormal values',
  'summary.noAbnormal': 'No values outside the reference range.',
  'summary.medications': 'Medications',
  'summary.itemsToReview': 'Items to review',
  'summary.resultsExplained': 'Your results, explained',
  'summary.noFindings': 'No individual results to explain.',
  'summary.whatThisMeans': 'What this means',
  'summary.questions': 'Questions you might ask your doctor',
  'col.test': 'Test',
  'col.name': 'Name',
  'col.value': 'Value',
  'col.reference': 'Reference',
  'col.flag': 'Flag',
  'col.previous': 'Previous',
  'col.date': 'Date',
  'col.change': 'Change',
  'col.thisReport': 'This report',
  'fields.loading': 'Loading extracted values…',
  'fields.failed': 'Could not load extracted values.',
  'fields.empty': 'No structured values were extracted.',
  'compare.loading': 'Loading comparison…',
  'compare.failed': 'Could not load the comparison.',
  'compare.empty': 'This report has no numeric lab values to compare.',
  'compare.noPrevious': 'No earlier report with the same tests yet — upload another to see changes over time.',
  'flag.normal': 'Normal',
  'flag.borderline': 'Borderline',
  'flag.abnormal': 'Abnormal',
  'flag.critical': 'Critical',
  'flag.unknown': 'No range',
} as const

export type MessageKey = keyof typeof en

const bn: Record<MessageKey, string> = {
  'tab.patient': 'রোগীর জন্য ব্যাখ্যা',
  'tab.doctor': 'ডাক্তারের সারাংশ',
  'tab.fields': 'সংগৃহীত তথ্য',
  'tab.compare': 'তুলনা',
  'doc.uploaded': 'আপলোড',
  'doc.confirmed': 'নিশ্চিত',
  'doc.openOriginal': 'মূল ফাইল খুলুন',
  'doc.openFailed': 'মূল ফাইলটি খোলা যায়নি।',
  'doc.viewTrends': 'প্রবণতা দেখুন',
  'doc.loading': 'রিপোর্ট লোড হচ্ছে…',
  'doc.notFound': 'রিপোর্টটি পাওয়া যায়নি অথবা এটি দেখার অনুমতি আপনার নেই।',
  'doc.back': 'ড্যাশবোর্ডে ফিরুন',
  'doc.confirmPrompt':
    'নিচের মানগুলো যাচাই করে রিপোর্টটি নিশ্চিত করুন। সারাংশ, ফ্ল্যাগ ও প্রবণতা কেবল নিশ্চিত রিপোর্ট থেকেই তৈরি হয়।',
  'doc.processing': 'রিপোর্টটি এখনও প্রক্রিয়াধীন ({status})। নিশ্চিত হলে সারাংশ দেখা যাবে।',
  'doc.awaitingPatient': 'রোগী রিপোর্টটি নিশ্চিত করলে সারাংশ ও তুলনা দেখা যাবে।',
  'summary.disclaimer':
    'শুধু তথ্যের জন্য — এটি রোগনির্ণয় নয়। এই রিপোর্টের নিশ্চিত মান থেকে তৈরি। যেকোনো সিদ্ধান্তের আগে আপনার ডাক্তারের সাথে কথা বলুন।',
  'summary.version': 'সংস্করণ',
  'summary.latest': 'সর্বশেষ',
  'summary.regenerate': 'আবার তৈরি করুন',
  'summary.regenerating': 'আবার তৈরি হচ্ছে…',
  'summary.loading': 'সারাংশ লোড হচ্ছে…',
  'summary.translating': 'বাংলায় অনুবাদ হচ্ছে… প্রস্তুত না হওয়া পর্যন্ত ইংরেজিতে দেখানো হচ্ছে।',
  'summary.translationFailed': 'এই মুহূর্তে বাংলা অনুবাদ পাওয়া যাচ্ছে না — ইংরেজিতে দেখানো হচ্ছে।',
  'summary.loadFailed': 'সারাংশটি লোড করা যায়নি। আবার চেষ্টা করতে রিফ্রেশ করুন।',
  'summary.pending': 'সারাংশ তৈরি হচ্ছে… সাধারণত এক মিনিটের কম সময় লাগে।',
  'summary.failed': 'সারাংশটি তৈরি করা যায়নি।',
  'summary.retryHint': ' আবার চেষ্টা করতে "আবার তৈরি করুন" চাপুন।',
  'summary.regenerateFailed': 'আবার তৈরি শুরু করা যায়নি। একটু পরে চেষ্টা করুন।',
  'summary.meta': 'সংস্করণ {version} · তৈরি {date}',
  'summary.noneNoted': 'কিছু উল্লেখ নেই।',
  'summary.chiefFindings': 'প্রধান পর্যবেক্ষণ',
  'summary.abnormalValues': 'অস্বাভাবিক মান',
  'summary.noAbnormal': 'কোনো মান রেফারেন্স সীমার বাইরে নেই।',
  'summary.medications': 'ওষুধ',
  'summary.itemsToReview': 'পর্যালোচনার বিষয়',
  'summary.resultsExplained': 'আপনার ফলাফলের ব্যাখ্যা',
  'summary.noFindings': 'ব্যাখ্যা করার মতো আলাদা কোনো ফলাফল নেই।',
  'summary.whatThisMeans': 'এর অর্থ কী',
  'summary.questions': 'আপনার ডাক্তারকে যা জিজ্ঞেস করতে পারেন',
  'col.test': 'পরীক্ষা',
  'col.name': 'নাম',
  'col.value': 'মান',
  'col.reference': 'রেফারেন্স',
  'col.flag': 'ফ্ল্যাগ',
  'col.previous': 'আগের',
  'col.date': 'তারিখ',
  'col.change': 'পরিবর্তন',
  'col.thisReport': 'এই রিপোর্ট',
  'fields.loading': 'সংগৃহীত মান লোড হচ্ছে…',
  'fields.failed': 'সংগৃহীত মান লোড করা যায়নি।',
  'fields.empty': 'কোনো কাঠামোবদ্ধ মান পাওয়া যায়নি।',
  'compare.loading': 'তুলনা লোড হচ্ছে…',
  'compare.failed': 'তুলনা লোড করা যায়নি।',
  'compare.empty': 'এই রিপোর্টে তুলনা করার মতো কোনো সংখ্যাগত ল্যাব মান নেই।',
  'compare.noPrevious': 'একই পরীক্ষার আগের কোনো রিপোর্ট এখনও নেই — সময়ের সাথে পরিবর্তন দেখতে আরেকটি আপলোড করুন।',
  'flag.normal': 'স্বাভাবিক',
  'flag.borderline': 'সীমারেখায়',
  'flag.abnormal': 'অস্বাভাবিক',
  'flag.critical': 'গুরুতর',
  'flag.unknown': 'সীমা নেই',
}

const DICTIONARIES: Record<Language, Record<MessageKey, string>> = { en, bn }

export function translate(
  language: Language,
  key: MessageKey,
  vars?: Record<string, string | number>,
) {
  let text: string = DICTIONARIES[language][key] ?? en[key]
  for (const [name, value] of Object.entries(vars ?? {})) {
    text = text.replace(`{${name}}`, String(value))
  }
  return text
}

export function useT() {
  const language = useLanguage()
  return (key: MessageKey, vars?: Record<string, string | number>) =>
    translate(language, key, vars)
}

/** Locale for dates and numbers; bn-BD renders Bangla digits and month names. */
export function useLocale() {
  return useLanguage() === 'bn' ? 'bn-BD' : 'en-US'
}
