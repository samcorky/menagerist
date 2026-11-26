# Item types and parent types

An item type says what kind of thing something is and which fields it has: a Film, a Record, a Poster. This page explains how to group related types under a **parent type**, and when a parent type is the right tool and when a choice field or a smart collection is.

## What a parent type is

Make one type a **subtype** of another and it uses the other type's fields as well as its own. The other type is its **parent type**. A type with no parent is a **top-level type**.

Take Memorabilia. Poster, Photo print and Action figure are all memorabilia: each has a condition, a size and whether it is framed. Put those three fields on Memorabilia and make the other three its subtypes. A Poster then has Condition, Size and Framed from Memorabilia, and adds only what suits a poster, such as the printing.

- **The parent's fields come with the subtype.** They are shown read-only in the subtype's editor under "Fields from Memorabilia" and on an item tagged "From Memorabilia". To change one, edit it on the parent.
- **A subtype adds its own fields.** They belong to it alone. A subtype cannot define a field with the same key as its parent's.
- **Search by the parent finds the subtypes.** Filtering or searching by Memorabilia lists posters, prints and figures together; filtering by Poster lists only posters.
- **A subtype shows its parent.** Wherever a type is named with room for it, a poster reads "Memorabilia › Poster". On a card it is just "Poster".
- **The parent may hold items too.** An item can be a Memorabilia that is none of the subtypes, such as a loose ticket.
- **Colour and icon are inherited** until the subtype sets its own.

There is one level only: a subtype cannot have subtypes of its own, and a type that has subtypes cannot become a subtype. A parent type with subtypes cannot be deleted until they are deleted or made top-level types.

## Making and changing one

Open **Item types**, edit a type, and choose **Subtype of**. Choosing no parent makes it a top-level type again.

When the choice puts fields at stake Menagerist asks first, and never changes what an item holds:

- **Attaching a type that has the same field as its new parent** ("Merge the shared fields?"): the two are combined. Where both are a list of choices the options are joined, so nothing already saved stops being one of them.
- **Making a subtype top-level** ("Make Action figure a top-level type?"): keep the parent's fields on it as its own, or hide them. Hidden fields keep their values on the items and can be brought back later.

When several subtypes each define the same field, the parent's editor offers to move it up to the parent in one step, so it is defined once.

## Which tool when

| You want to... | Use | Why |
| -------------- | --- | --- |
| Share fields between types that are different kinds of one thing, and see them together or apart | A **parent type** | The subtypes share the parent's fields, and each can add its own. |
| Record a label that does not change which fields apply, such as a poster's printing or an item's condition | A **choice field** | One type, one list of options. There is nothing to share, so a subtype would add a type for no reason. |
| Gather items by a rule or by hand, across types, such as everything marked Wanted or the posters on the wall | A **smart collection** or a collection | A collection can hold items of any type and can be built from a search. It does not give items fields. |

A few rules of thumb:

- If the things need **different fields**, they are different types, and if those types also **share** fields, make them subtypes of one parent.
- If they need **the same fields** and differ only in a label, use one type with a choice field.
- If you want a list that **cuts across types**, or changes as items change, use a smart collection.

## Examples

- **Memorabilia** with Poster, Ticket stub and Programme: condition and price paid on the parent; a poster's size, a stub's screening date and seat, a programme's page count on the subtype. The Movies example pack sets this up, and the Comic con pack does the same with Collectable (Poster, Photo print and Programme).
- **Music media** with Vinyl, CD, Cassette and MiniDisc: artist, title, label, catalogue number and condition on the parent; speed and pressing for Vinyl, an edition for CD. The "Record formats" example pack sets this up, and its "Remaster of" connection joins a CD to the vinyl it came from.
- **Currency** with Coin, Banknote and Token, and **Film media** with Laser Disc, DVD, Blu-ray and VHS, are example packs too. Add one from **Examples** to see a parent type working before you build your own.

A connection type can also be limited to a parent type, and then it covers every subtype: "Remaster of" can join any music media to any other.
