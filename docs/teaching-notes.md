# Teaching notes: one checkout, told slowly

Use this with beginners. The screen they look at is http://localhost:8000/. Stay on the **Lesson** tab and read the rust-colored box out loud. It changes after each click. These notes are the same lesson, with the answers written down so you can walk the room.

Plan on about 50 minutes. Reset the lab before the next group.

## What you are teaching

A shop used to keep an order, the stock, the payment, and the email inside one program. We split that work into small programs. Each small program keeps its own notebook.

The purchase in class is always the same: **2 units of product A1**, order name **o-104**, repeat ticket **demo-1**.

You are not teaching them to memorize tool names. You are teaching four habits:

1. Only the program that owns the data is allowed to change it.
2. Pressing the button twice must not buy twice.
3. If we do not know whether the money was taken, we do not put the stock back.
4. We do not pretend an email was sent.

Stripe and email are real. This lab does not invent a successful payment or a successful email. Say that in the first five minutes, so nobody thinks the red "not configured" chips are a bug.

## Words to introduce when you reach them

| Word on the screen | Say it this way |
|---|---|
| Service | A small program with one job. |
| Gateway | The front door. It does not own the stock or the order. It carries our click to the program that does. |
| Legacy | The old program. We still let it answer "how many are left?" We do not let it sell anything. |
| Reservation | A hold. Those units are no longer free to sell. |
| Repeat ticket | The idempotency key. Same ticket and same details means "you already did this." |
| PAYMENT_UNKNOWN | We do not know if the money was taken. |
| Reconcile | Ask the payment company again, then decide. |
| Outbox | A note saved in the same step as "order confirmed," so we cannot lose the request to send mail. |
| RabbitMQ | A waiting line for that note. |
| 365 ms | About one third of a second. A speed target we measure. A slow call is still accepted. |

## Before they arrive

1. `docker compose ps` shows the app containers running, Postgres and RabbitMQ healthy, and `schema-init` already exited. That exit is success. It created the notebooks and stopped.
2. Open http://localhost:8000/. Both stock numbers must say **5**. The chips say Stripe is not configured and SMTP is not configured, unless you added real keys.
3. If a previous group left an order behind, press **Reset lab** and confirm.

## Step 1. Two copies of the stock

**Say:** "We have one product, A1. The new inventory program has 5. The old program also has 5. They are not the same shelf. When we buy something, only the new number is allowed to move."

**They do:** Read the two cards. Do not click yet.

**They should see:** Inventory 5, Legacy 5. The first checklist line turns green because both programs answered.

**If someone asks why we still have the old program:** We are moving the shop one door at a time. The old door still answers questions. The new door takes the sale. We call that a strangler move: the new path grows around the old one, and the old write path is switched off.

## Step 2. Place the order

**Say:** "Press Submit checkout. Watch only the new number."

**They do:** Press **Submit checkout**. Leave every field as it is: order `o-104`, product `A1`, quantity `2`, ticket `demo-1`.

**They should see:**

- The new stock falls from 5 to **3**.
- The old stock stays at **5**.
- The boxes say Stock "3 available," Reserve "2 reserved," Payment "Unknown."
- The line under the form says the shelf held the units and payment did not say yes or no.

**The idea:** The order program did not reach into the stock notebook and edit it. It asked the inventory program to hold 2 units. The inventory program subtracted only because it still had enough. It cannot go below zero.

**Why payment is unknown:** Stripe is not configured, so no charge was attempted. The order is saved as `PAYMENT_UNKNOWN`. We keep the hold. Unsure is not the same as "the payment failed."

Point at the top chips while you say that.

## Step 3. Press the button again

**Say:** "A customer on a slow network will press the button twice. Do it. Do not change anything in the form."

**They do:** Press **Submit checkout** again.

**They should see:** "Same ticket, same details. This is still order o-104. Nothing new was held." Stock stays **3**.

**The idea:** The repeat ticket `demo-1` already belongs to this exact purchase. The order program returns the original order. This is called a replay. The shelf is not asked to hold another 2 units.

## Step 4. Change the quantity

**Say:** "Now change the quantity to 9. Keep the ticket as demo-1. One ticket cannot mean two different purchases."

**They do:** Set quantity to **9**. Press **Submit checkout**.

**They should see:** "Refused. Idempotency key payload mismatch." Stock stays **3**. The hold stays.

**If someone asks what "payload" means:** The details of the request. The ticket was already used for quantity 2. Quantity 9 is a different request, so the lab refuses instead of guessing which one the customer wanted.

Put the quantity back to 2 after they have seen the refusal, so the form matches the real order again. The refusal is already recorded for the checklist.

## Step 5. Reconcile

**Say:** "We still do not know about the money. Press Reconcile. That means: ask Stripe again, then decide. Do not give the stock back while the answer is missing."

**They do:** Press **Reconcile**.

**They should see:** "Payment outcome cannot be verified; reservation retained." Stock stays **3**. The hold stays `reserved`.

**The idea:** A timeout, a missing key, or a program that crashed in the middle is an unknown result. The safe shop keeps the hold and asks the payment company. It does not invent a failure and it does not invent a success.

The rust box should now say the lesson is complete and send them to the other two tabs.

## Step 6. Name the tables

Open **Live board**. Ask different students to read one heading each.

| Table | What a beginner should be able to say |
|---|---|
| Orders | There is one purchase, o-104, for 2 units, status PAYMENT_UNKNOWN. |
| Reservations | Those 2 units are on hold. |
| Outbox | Empty. A note is written only when the order becomes confirmed. |
| Payments | Empty. Stripe was never reached, so nothing was stored. |
| Notifications | Empty. No email was accepted. |
| Waiting line | RabbitMQ is up. The email program is connected. There is no message, because the order was never confirmed. |

**Say:** "Empty is an honest answer. We do not draw a fake payment or a fake email to make the table look finished."

## Step 7. Look at the clock

Open **Telemetry**.

**Say:** "Each bar is how long that program took on the real checkout calls. The dark line is 365 milliseconds, about one third of a second. It is a target we agreed to look at. Nothing in this lab rejects a call for being slower. The dashboard's own refresh is not counted, so the bars are about the purchase, not about this page redrawing."

If the bars are well under the line, say so. If one is over the line, that is a useful result, not a broken demo. Payment and inventory were called during the purchase, so their counts should be at least 1.

Prometheus at http://localhost:9090 is the same measurements drawn over time. RabbitMQ's own page is http://localhost:15672, user `guest`, password `guest`. You do not need either page to finish the lesson.

## What you tell them this lab will not do

- It will not mark the order paid without Stripe.
- It will not send mail without real SMTP settings.
- It will not move the old program's stock. Legacy writes are switched off.
- The programs share one database login in this classroom. Separate notebooks are a rule the code follows. The database is not locking each program out of the others' tables. Say that if a student asks whether this is production isolation.
- The old program is an example we started beside the new one. It is not a copy of a live shop's data.

## If you later add a Stripe test key

Put `STRIPE_SECRET_KEY` in `.env` and run `docker compose up -d`. Reset the lab. Place the order again.

**They should see:** status `AWAITING_PAYMENT`, a PaymentIntent id, and a client secret. Say, clearly, that a PaymentIntent is a started payment. It is not a charge. Confirm it with Stripe's own test-card page. Do not type a card number into this lab. Then press **Reconcile**.

If Stripe says the payment succeeded, the order becomes **CONFIRMED**. Then show them:

- The new stock stays at 3, because the units were sold.
- An outbox row appears. It was saved in the same step as the confirmed order.
- Within a couple of seconds the worker hands that note to RabbitMQ and marks it published.
- With SMTP filled in, a notification row appears after the mailbox accepts the message. Say that a crash after the mailbox accepts it can send the same email twice. The waiting line gives at-least-once delivery.

If Stripe says the payment was canceled, Reconcile releases the hold and the stock goes back up.

## Reset between groups

Press **Reset lab** and confirm. Both stock numbers return to 5. The practice order, the hold, any stored payment, any mail record, and any waiting message are removed.

If the form still says quantity 9, set it back to 2 and set the ticket back to `demo-1` before the next group starts.

## If a strong student asks where the code is

Keep this for after the clicks. Do not start here.

| What they just saw | Where it lives |
|---|---|
| The front door and this page | `api-gateway/` |
| The order, the repeat ticket, and the outbox note | `order-service/main.py` |
| The shelf and the hold | `inventory-service/main.py` |
| The call to Stripe | `payment-service/main.py` |
| The worker that hands the note to RabbitMQ | `outbox-worker/main.py` |
| The program that sends mail | `event-consumer/main.py` |
| The old stock | `legacy-monolith/main.py` |
| The short design decision | `docs/ADR.md` |

The decision record says we keep each save inside one program, we use repeat tickets, we write the outbox note in the same save as the confirmed order, and we ask Stripe again before we confirm or give the stock back.
