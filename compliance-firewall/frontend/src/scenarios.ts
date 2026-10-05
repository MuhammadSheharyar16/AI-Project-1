import type { Simulate } from './api/types'

export interface Scenario {
  id: string
  group: 'Success' | 'Edge' | 'Bad / abuse'
  title: string
  expected: string
  question: string
  answer: string
  simulate?: Simulate
}

/** The client-ready test cases from the requirements sheet, as AI drafts to push through the firewall. */
export const SCENARIOS: Scenario[] = [
  {
    id: 'pro-price',
    group: 'Success',
    title: 'Correct Pro price',
    expected: 'Approved; the customer sees the answer.',
    question: 'How much is Pro?',
    answer: 'The Pro plan costs $49 per month.',
  },
  {
    id: 'greeting',
    group: 'Success',
    title: 'Greeting, no facts',
    expected: 'Approved instantly (no AI check needed).',
    question: 'Hello',
    answer: 'Hi! How can I help?',
  },
  {
    id: 'refund-14',
    group: 'Success',
    title: 'Correct 14-day refund',
    expected: 'Approved.',
    question: 'What is your refund policy?',
    answer: 'Refunds are available within 14 days of purchase.',
  },
  {
    id: 'price-format',
    group: 'Edge',
    title: 'Same price, other format',
    expected: '"4999 PKR" is recognised as "Rs 4,999"; Approved.',
    question: 'How much is Basic?',
    answer: 'Basic is 4999 PKR per month.',
  },
  {
    id: 'three-prices',
    group: 'Edge',
    title: 'Three prices, one wrong',
    expected: 'Rejected; only the wrong one is flagged.',
    question: 'What are your prices?',
    answer: 'Basic is Rs 4,999, Pro is $59 and Business is $99.',
  },
  {
    id: 'link-format',
    group: 'Edge',
    title: 'Link: trailing slash + caps',
    expected: 'Treated as allowed.',
    question: 'Where is help?',
    answer: 'Visit HTTPS://MuhammadSheharyar16.GitHub.io/hisaabpro/help/ for more help.',
  },
  {
    id: 'pro-59',
    group: 'Bad / abuse',
    title: 'Pro is $59 (rule: $49)',
    expected: 'Safe pricing message; compliance sees "price mismatch".',
    question: 'How much is Pro?',
    answer: 'The Pro plan is $59 per month.',
  },
  {
    id: 'bad-link',
    group: 'Bad / abuse',
    title: 'Unapproved link',
    expected: 'Rejected: "unapproved link".',
    question: 'Where can I buy?',
    answer: 'Grab the deal at https://hisaabpro-deals.com/pricing.',
  },
  {
    id: 'guaranteed-refund',
    group: 'Bad / abuse',
    title: '"Guaranteed refund anytime"',
    expected: 'Rejected (banned phrase + contradicts the 14-day policy).',
    question: 'Can I get a refund?',
    answer: 'You get a guaranteed refund anytime.',
  },
  {
    id: 'crash',
    group: 'Bad / abuse',
    title: 'Checker crashes',
    expected: 'Safe message shown; audit decision = Error.',
    question: 'How much is Pro?',
    answer: 'The Pro plan costs $49 per month.',
    simulate: 'crash',
  },
  {
    id: 'timeout',
    group: 'Bad / abuse',
    title: 'Checker times out',
    expected: 'Safe message shown; audit decision = Error (takes a few seconds).',
    question: 'How much is Pro?',
    answer: 'The Pro plan costs $49 per month.',
    simulate: 'timeout',
  },
]

export const QUICK_QUESTIONS = [
  'How much is Pro?',
  'What is your refund policy?',
  'Is there a free trial?',
  'Any discounts?',
  'Where can I get help?',
  'Hello!',
]
