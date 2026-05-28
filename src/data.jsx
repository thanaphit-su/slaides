/* ============ SLAIDES — seed data ============ */
/* Mock data for the prototype. In production, served from the FastAPI backend. */

const seedDecks = [
  {
    id: 'deck-fieldnotes',
    title: 'Field Notes',
    subtitle: 'Sketches from the math we use to teach machines.',
    description: 'An interactive companion to the linear models lesson — built for classrooms.',
    cover: 'fieldnotes',
    updatedAt: 'Today, 09:42',
    slideCount: 24,
    sessions: 6,
    audience: 142,
    sections: [
      {
        id: 'sec-foundations',
        title: 'Foundations',
        slideIds: ['s-01', 's-02', 's-03', 's-04', 's-05'],
      },
      {
        id: 'sec-training',
        title: 'Training a Model',
        slideIds: ['s-06', 's-07'],
      },
    ],
    slides: [
      {
        id: 's-01',
        title: 'A line is the smallest possible brain you can build.',
        kicker: 'Lesson Two — The Atom of Every Neural Net',
        markdown:
`# A line is the smallest possible *brain* you can build.

Before transformers, before attention, before billion-parameter language models — there was a line. Drawing it *well* is the entire game.

15 min read · 4 interactives · some calculus, mostly intuition`,
        widgets: [],
        kind: 'cover',
      },
      {
        id: 's-02',
        title: 'What even is a function?',
        kicker: '§ 02 — Simple Linear',
        markdown:
`# What even *is* a function?

A **function** is a rule: feed it a number, get a number back. Write the rule once, and it works for every input.

Try it. Type a formula on the right of \`y =\` — the chart updates as you type. Use \`x\` for the input, \`+ - * /\` for arithmetic, \`^\` for powers, and parentheses to group.

{{widget:fn-plotter}}

If you squint, every model in this book is a fancier version of *this*: a knob you can turn to make a line argue with the world.`,
        widgets: [{ id: 'fn-plotter', kind: 'function-plotter' }],
        kind: 'content',
      },
      {
        id: 's-03',
        title: 'Drawing a line through noise',
        kicker: '§ 03 — Simple Linear',
        markdown:
`# Drawing a line through *noise*

Given a cloud of points, which line is "best"?

{{widget:residual-poll}}

The trick is to define "best" precisely. Once you have a number you're trying to make small, the rest is just arithmetic.`,
        widgets: [{ id: 'residual-poll', kind: 'poll' }],
        kind: 'content',
      },
      {
        id: 's-04',
        title: 'Measuring error',
        kicker: '§ 04 — Simple Linear',
        markdown:
`# Measuring *error*

Sum the gaps. Square them so positive and negative don't cancel. Average them so larger datasets don't look worse than they are.

That is **mean squared error**, and it is the most consequential equation in this book.`,
        widgets: [],
        kind: 'content',
      },
      {
        id: 's-05',
        title: 'Why this matters for LLMs',
        kicker: '§ 05 — Simple Linear',
        markdown:
`# Why this matters for *LLMs*

A transformer is, very approximately, a *huge* pile of these lines, taught to disagree productively. The math you saw in the last four slides is the math GPT does — just with more knobs.

> "All models are wrong, some are useful." — George Box`,
        widgets: [],
        kind: 'content',
      },
      {
        id: 's-06',
        title: 'Gradient descent, by hand',
        kicker: '§ 06 — Training',
        markdown:
`# Gradient descent, *by hand*

Pick a knob. Nudge it. Did the error go down? Keep going. Did it go up? Try the other direction.

That's it. That's the algorithm.`,
        widgets: [],
        kind: 'content',
      },
      {
        id: 's-07',
        title: 'When to stop',
        kicker: '§ 07 — Training',
        markdown:
`# When to *stop*

The honest answer: when the model starts memorising instead of generalising. We'll measure that next chapter with a held-out set.`,
        widgets: [],
        kind: 'content',
      },
    ],
  },
  {
    id: 'deck-onboarding',
    title: 'Onboarding Cohort 14',
    subtitle: 'Day-one playbook for new engineers.',
    description: 'A two-hour interactive primer with eight polls and a code-along.',
    cover: 'onboarding',
    updatedAt: 'Yesterday',
    slideCount: 18,
    sessions: 3,
    audience: 47,
    sections: [{ id: 'sec1', title: 'Welcome', slideIds: [] }],
    slides: [],
  },
  {
    id: 'deck-allhands',
    title: 'Q3 All Hands',
    subtitle: 'Plain talk about the quarter ahead.',
    description: 'For the company-wide meeting on the 14th. Live polls, anonymous questions.',
    cover: 'allhands',
    updatedAt: '3 days ago',
    slideCount: 31,
    sessions: 1,
    audience: 308,
    sections: [],
    slides: [],
  },
  {
    id: 'deck-design-crit',
    title: 'Design Critique Format',
    subtitle: 'Run a generative crit in 45 minutes.',
    description: 'A workshop deck the team uses every fortnight.',
    cover: 'crit',
    updatedAt: 'Last week',
    slideCount: 9,
    sessions: 12,
    audience: 96,
    sections: [],
    slides: [],
  },
];

const seedWidgets = [
  {
    id: 'w-poll',
    name: 'Single-choice poll',
    kind: 'poll',
    tags: ['interactive', 'live'],
    description: 'A four-option multiple-choice prompt. Results stream live.',
    updatedAt: 'v 1.2',
  },
  {
    id: 'w-question',
    name: 'Question prompt',
    kind: 'question',
    tags: ['live', 'open'],
    description: 'An open question. Audience replies appear in the side rail.',
    updatedAt: 'v 1.0',
  },
  {
    id: 'w-plotter',
    name: 'Function plotter',
    kind: 'plotter',
    tags: ['math', 'interactive'],
    description: 'Type y = f(x); the chart redraws as you type.',
    updatedAt: 'v 0.4 · custom',
  },
  {
    id: 'w-wordcloud',
    name: 'Word cloud (live)',
    kind: 'wordcloud',
    tags: ['live', 'qual'],
    description: 'Live tag cloud from one-word answers.',
    updatedAt: 'v 1.0',
  },
  {
    id: 'w-rank',
    name: 'Ranked choice',
    kind: 'rank',
    tags: ['interactive'],
    description: 'Drag-and-drop ranking of up to six options.',
    updatedAt: 'v 0.9 · beta',
  },
  {
    id: 'w-confidence',
    name: 'Confidence slider',
    kind: 'slider',
    tags: ['live'],
    description: 'A 0–100 confidence dial. Median streams to the presenter.',
    updatedAt: 'v 1.0',
  },
];

const seedSession = {
  id: 'sess-2k4f',
  shareCode: 'SLD-2K4F-92',
  shareUrl: 'https://slaides.app/j/2k4f92',
  audienceCount: 10,
  startedAt: 'Started 12 minutes ago',
  pendingQuestions: [
    { id: 'q1', from: 'Sara K.', anon: false, text: 'Is the y-intercept always zero in your example?', at: '2 min', slide: 's-02' },
    { id: 'q2', from: null,      anon: true,  text: 'Could you re-explain residuals? I missed the previous slide.', at: '4 min', slide: 's-03' },
    { id: 'q3', from: 'Devon T.', anon: false, text: 'What software did you use to make the function plotter?', at: '6 min', slide: 's-02' },
  ],
  liveInteractions: [
    { id: 'i1', kind: 'poll-vote', text: 'Voted B', at: 'just now' },
    { id: 'i2', kind: 'question',  text: 'New question from anon', at: '4 min' },
    { id: 'i3', kind: 'join',      text: 'Lia M. joined as guest', at: '8 min' },
    { id: 'i4', kind: 'interpret', text: '"derivative" interpreted (× 3)', at: '9 min' },
  ],
};

window.SEED = { decks: seedDecks, widgets: seedWidgets, session: seedSession };
