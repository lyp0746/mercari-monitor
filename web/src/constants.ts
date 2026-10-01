export const PLATFORM_NAMES: Record<string, string> = {
  mercari_jp: 'Mercari JP',
  bunjang: 'Bunjang 번장',
  paypay_fleamarket: 'PayPay フリマ',
  fril: 'Fril (Rakuma)',
  yahoo_auctions: 'Yahoo! Auctions',
  carousell: 'Carousell',
  surugaya: '駿河屋',
  rakuten: '楽天市場',
  yahoo_shopping: 'Yahoo!ショッピング',
}

export const PLATFORM_EMOJI: Record<string, string> = {
  mercari_jp: '🇯🇵',
  bunjang: '🇰🇷',
  paypay_fleamarket: '🇯🇵',
  fril: '🇯🇵',
  yahoo_auctions: '🇯🇵',
  carousell: '🌏',
  surugaya: '🇯🇵',
  rakuten: '🇯🇵',
  yahoo_shopping: '🇯🇵',
}

export const PLATFORM_LIST = [
  { id: 'mercari_jp', name: 'Mercari JP', emoji: '🇯🇵', region: '日本', type: '二手C2C', status: 'stable' as const },
  { id: 'yahoo_auctions', name: 'Yahoo! Auctions', emoji: '🇯🇵', region: '日本', type: '拍卖C2C', status: 'stable' as const },
  { id: 'surugaya', name: '駿河屋', emoji: '🇯🇵', region: '日本', type: '动漫/中古', status: 'stable' as const },
  { id: 'rakuten', name: '楽天市場', emoji: '🇯🇵', region: '日本', type: '新品B2C', status: 'stable' as const },
  { id: 'yahoo_shopping', name: 'Yahoo!ショッピング', emoji: '🇯🇵', region: '日本', type: '新品B2C', status: 'stable' as const },
  { id: 'paypay_fleamarket', name: 'PayPay フリマ', emoji: '🇯🇵', region: '日本', type: '二手C2C', status: 'unstable' as const },
  { id: 'fril', name: 'Fril (Rakuma)', emoji: '🇯🇵', region: '日本', type: '二手C2C', status: 'unstable' as const },
  { id: 'bunjang', name: 'Bunjang 번장', emoji: '🇰🇷', region: '韩国', type: '二手C2C', status: 'stable' as const },
  { id: 'carousell', name: 'Carousell', emoji: '🌏', region: 'SG/HK/TW/MY/PH/AU', type: '二手C2C', status: 'slow' as const },
]