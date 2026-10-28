import type { Contact } from "../../api/types";

/** Only the channels that exist. Links only: no application form (PUB-7). */
export function ContactLinks({ contact }: { contact: Contact }) {
  return (
    <ul className="contact-links">
      {contact.url && (
        <li>
          <a href={contact.url} target="_blank" rel="noopener noreferrer">
            Open the shelter's page
          </a>
        </li>
      )}
      {contact.email && (
        <li>
          <a href={`mailto:${contact.email}`}>Email {contact.email}</a>
        </li>
      )}
      {contact.phone && (
        <li>
          <a href={`tel:${contact.phone}`}>Call {contact.phone}</a>
        </li>
      )}
    </ul>
  );
}
