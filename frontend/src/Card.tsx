import type { Component } from 'solid-js';
import type { Event } from './event';

type EventProps = {
  event: Event
}

const Card: Component<EventProps> = (props) => {
  return (
    <a href={props.event.source_url} class='flex flex-col gap-6 border-1 p-3 shadow-md rounded-xl w-100 '>
      <div class='flex justify-between'>
        <h1 class='font-bold'>{props.event.event_title}</h1>
        <h2 class='font-semibold'>org</h2>
      </div>
      <p>{props.event.description || "empty"}</p>
      <div class='flex justify-between gap-4 mt-2'>
        <p>start (- end)</p>
        <p>{props.event.location}</p>
      </div>
    </a>
  );
};

export default Card;
