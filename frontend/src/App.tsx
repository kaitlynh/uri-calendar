import type { Component } from 'solid-js';
import Header from './Header';
import Card from './Card';
import { Event } from './event';

const TEST_DATA: Event[] = [
  {
    event_id: "1",
    source_url: "empty",
    event_title: "The first title",
    start_datetime: "Tuesday",
    end_datetime: "also Tuesday",
    location: "Here",
    description: "",
    extracted_at: "",
  },
  {
    event_id: "2",
    source_url: "empty",
    event_title: "The second title",
    start_datetime: "Tuesday",
    end_datetime: "also Tuesday",
    location: "Here",
    description: "",
    extracted_at: "",
  },
  {
    event_id: "3",
    source_url: "empty",
    event_title: "Actual title",
    start_datetime: "Tuesday",
    end_datetime: "also Tuesday",
    location: "Here",
    description: "",
    extracted_at: "",
  },
  {
    event_id: "4",
    source_url: "empty",
    event_title: "So many titles",
    start_datetime: "Tuesday",
    end_datetime: "also Tuesday",
    location: "Here",
    description: "",
    extracted_at: "",
  }
];

const App: Component = () => {
  return (
    <>
      <Header />
      <main class='flex flex-col items-center gap-3 p-3'>

        <section>
          <h2>Today</h2>
          <Card event={TEST_DATA[0]} />
          <Card event={TEST_DATA[1]} />
        </section>
        <section>
          <h2>Tomorrow</h2>
          <Card event={TEST_DATA[2]} />
          <Card event={TEST_DATA[3]} />
        </section>
      </main>
    </>
  );
};

export default App;
