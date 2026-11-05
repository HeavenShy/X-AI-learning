import type { Question, Quiz } from '../src/types/api'

export const single: Question = {
  id: 'q1',
  type: 'single',
  stem: 'RAG 这个词里的 R，指的是什么？',
  options: [
    { key: 'A', text: '检索（Retrieval）' },
    { key: 'B', text: '推理（Reasoning）' },
    { key: 'C', text: '排序（Ranking）' },
    { key: 'D', text: '改写（Rewrite）' }
  ],
  answer: ['A'],
  explanation: 'RAG 全称 Retrieval-Augmented Generation，意思是“检索增强生成”。',
  knowledge_point: 'RAG 的基本定义',
  difficulty: 'easy'
}

export const judge: Question = {
  id: 'q2',
  type: 'judge',
  stem: '用了 RAG 之后，大模型就不再需要任何训练了。',
  options: [
    { key: 'A', text: '对' },
    { key: 'B', text: '错' }
  ],
  answer: ['B'],
  explanation: 'RAG 不替代训练。',
  knowledge_point: 'RAG 和模型训练的关系',
  difficulty: 'medium'
}

export const multiple: Question = {
  id: 'q3',
  type: 'multiple',
  stem: '下面哪些是 RAG 相比纯大模型回答的优势？',
  options: [
    { key: 'A', text: '能用上最新的外部资料' },
    { key: 'B', text: '回答从此完全不会出错' },
    { key: 'C', text: '回答可以追溯到出处' },
    { key: 'D', text: '不需要准备任何资料' }
  ],
  answer: ['A', 'C'],
  explanation: 'B 错在“完全”：RAG 能减少胡编。\nA 该选：资料更新了，答案也跟着更新。',
  knowledge_point: 'RAG 的优势与边界',
  difficulty: 'hard'
}

export const quiz: Quiz = {
  quiz_id: 'quiz_abc',
  title: 'RAG 入门',
  summary: 'RAG 是什么、检索和生成怎么分工。',
  source_type: 'text',
  user_input: '我想学习什么是 RAG',
  questions: [single, judge, multiple]
}
