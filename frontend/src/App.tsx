import { createResource, For, Match, Suspense, Switch, type Component } from 'solid-js';
import Header from './Header';
import Card from './Card';
import { Event } from './event';

const TEST_DATA: Event[] = [
  {
    event_id: "1",
    source_name: "Kantonsbibliothek",
    source_url: "",
    event_title: "Lesen für Alle",
    start_date: "Tuesday",
    start_time: "Tuesday",
    end_datetime: "also Tuesday",
    location: "Bi de Bib",
    description: "Lesen tut allen gut. Auch dir",
    extracted_at: "",
  },
  {
    event_id: "2",
    source_name: "Toni",
    source_url: "",
    event_title: "Eis go neh",
    start_date: "Tuesday",
    start_time: "Tuesday",
    end_datetime: "also Tuesday",
    location: "Bäre",
    description: "Gmüetlichs zemesii",
    extracted_at: "",
  },
  {
    event_id: "3",
    source_name: "Gemeinde Altdorf",
    source_url: "",
    event_title: "Fasnacht",
    start_date: "Tuesday",
    start_time: "Tuesday",
    end_datetime: "also Tuesday",
    location: "Wie immer",
    description: "Iitrummele, aber dasmal alli im Takt bliibe",
    extracted_at: "",
  },
  {
    event_id: "4",
    source_name: "Granit Boulder",
    source_url: "",
    event_title: "Full Send Sunday",
    start_date: "Tuesday",
    start_time: "Tuesday",
    end_datetime: "also Tuesday",
    location: "Bim Otto's",
    description: "Klettern.",
    extracted_at: "",
  }
];


const dayHeaderClasses = 'font-bold text-lg sticky top-0 bg-white block px-4 w-[100%] text-center mt-4';

// TODO: hardcoded silliness
const today = '2026-03-27';
const api = `http://178.104.80.19/api/events?date=${today}`;

const fetchDataToday = async () => {
  const response = await fetch(api);
  return response.json();
}

const App: Component = () => {

  const [events] = createResource(fetchDataToday)


  return (
    <>
      <Header />
      <main class='flex flex-col items-center gap-3 px-10 py-4'>
        <Suspense fallback={<div>Loading...</div>}>
          <Switch>
            <Match when={events.error}>
              <span>Something broke</span>
            </Match>
            <Match when={events()}  >
              <h2 class={dayHeaderClasses}>Heute</h2>
              <For each={events()}>
                {(item, _index) =>
                  <Card event={item} />
                }
              </For>
            </Match>
          </Switch>
        </Suspense>
      </main>
    </>
  );
};

export default App;
