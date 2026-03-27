import type { Component } from 'solid-js';
import Header from './Header';
import Card from './Card';
import { Event } from './event';

const TEST_DATA: Event[] = [
  {
    event_id: "1",
    source_url: "",
    event_title: "The first title",
    start_datetime: "Tuesday",
    end_datetime: "also Tuesday",
    location: "Here",
    description: "let me tell you the story of darth plagueis, the wise. lorem ipsum dolor simet",
    extracted_at: "",
  },
  {
    event_id: "2",
    source_url: "",
    event_title: "The second title",
    start_datetime: "Tuesday",
    end_datetime: "also Tuesday",
    location: "Here",
    description: "",
    extracted_at: "",
  },
  {
    event_id: "3",
    source_url: "",
    event_title: "Actual title",
    start_datetime: "Tuesday",
    end_datetime: "also Tuesday",
    location: "Here",
    description: "",
    extracted_at: "",
  },
  {
    event_id: "4",
    source_url: "",
    event_title: "So many titles",
    start_datetime: "Tuesday",
    end_datetime: "also Tuesday",
    location: "Here",
    description: "let me ",
    extracted_at: "",
  }
];


const dayHeaderClasses = 'font-bold text-lg sticky top-0 bg-white block px-4 w-[100%] text-center mt-4';

const App: Component = () => {

  return (
    <>
      <Header />
      <main class='flex flex-col items-center gap-3 px-10 py-4'>
        <h2 class={dayHeaderClasses}>Heute</h2>
        <Card event={TEST_DATA[0]} />
        <Card event={TEST_DATA[1]} />

        <h2 class={dayHeaderClasses}>Morgen</h2>
        <Card event={TEST_DATA[2]} />
        <Card event={TEST_DATA[3]} />

        <h2 class={dayHeaderClasses}>In zwei Tagen</h2>
        <Card event={TEST_DATA[2]} />
        <Card event={TEST_DATA[3]} />

        <h2 class={dayHeaderClasses}>In drei Tagen</h2>
        <Card event={TEST_DATA[2]} />
        <Card event={TEST_DATA[3]} />
        <h2 class={dayHeaderClasses}>In vier Tagen</h2>
        <Card event={TEST_DATA[2]} />
        <Card event={TEST_DATA[3]} />
      </main>
    </>
  );
};

export default App;
