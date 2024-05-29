from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse
import db
import generic_helper

app = FastAPI()
inprogress_orders = {}

@app.post("/")
async def handle_request(request: Request):
    # Retrieve the JSON data from the request
    payload = await request.json()
    # Extract the necessary information from the payload
    # based on the structure of the WebhookRequest from Dialogflow
    intent = payload['queryResult']['intent']['displayName']
    parameters = payload['queryResult']['parameters']
    output_contexts = payload['queryResult']['outputContexts']

    session_id = generic_helper.extract_session_id(output_contexts[0]['name'])

    intent_handler_dict = {
        'Order.add - context: ongoing-order': add_to_order,
        'order.remove - context: ongoing-order': remove_from_order,
        'order.complete - context: ongoing-order': complete_order,
        'track.order - context: ongoing-tracking': track_order
    }

    return intent_handler_dict[intent](parameters, session_id)

def remove_from_order(parameters: dict, session_id: str):
    if session_id not in inprogress_orders:
        return JSONResponse(content={
            "fulfillmentText": "I'm having a trouble finding your order. Sorry! Can you place a new order please?"
        })
    
    current_order=inprogress_orders[session_id]
    watch_items = parameters["watch-item"]

    removed_items = []
    no_such_items = []

    for item in watch_items:
        if item not in current_order:
            no_such_items.append(item)
        else:
            removed_items.append(item)
            del current_order[item]

    if len(removed_items) > 0:
        fulfillment_text = f'Removed {",".join(removed_items)} from your order!'

    if len(no_such_items) > 0:
        fulfillment_text = f' Your current order does not have {",".join(no_such_items)}'

    if len(current_order.keys()) == 0:
        fulfillment_text += " Your order is empty!"
    else:
        order_str = generic_helper.get_str_from_watch_dict(current_order)
        fulfillment_text += f" Here is what is left in your order: {order_str}"

    return JSONResponse(content={
            "fulfillmentText": fulfillment_text
    })


def add_to_order(parameters: dict, session_id: str):
    watch_items = parameters["watch-item"]
    quantities = parameters["number"]

    if len(watch_items) != len(quantities):
        fulfillment_text = "Sorry I didn't understand. Can you please specify food items and quantities clearly?"
    else:
        new_watch_dict = dict(zip(watch_items, quantities))

        if session_id in inprogress_orders:
            current_watch_dict=inprogress_orders[session_id]
            current_watch_dict.update(new_watch_dict)
            inprogress_orders[session_id] = current_watch_dict
        else:
            inprogress_orders[session_id]= new_watch_dict

        order_str = generic_helper.get_str_from_watch_dict(inprogress_orders[session_id])
        fulfillment_text = f"So far you have: {order_str}. Do you need anything else?"


    return JSONResponse(content={
            "fulfillmentText": fulfillment_text
    })

def complete_order(parameters: dict, session_id: str):
    if session_id not in inprogress_orders:
        fulfillment_text = "I'm having a trouble finding your order. Sorry! Can you place a new order please?"
    else:
        order = inprogress_orders[session_id]
        order_id = save_to_db(order)

        if order_id == -1:
            fulfillment_text = "Sorry, I couldn't process your order due to a backend error. " \
                               "Please place a new order again"
        else:
            order_total = db.get_total_order_price(order_id)
            fulfillment_text = f"Awesome. We have placed your order. " \
                               f"Here is your order id # {order_id}. " \
                               f"Your order total is {order_total} which you can pay at the time of delivery!"
            
        del inprogress_orders[session_id]

    return JSONResponse(content={
            "fulfillmentText": fulfillment_text
    })

def save_to_db(order: dict):
    next_order_id = db.get_next_order_id()

    for watch_item, quantity in order.items():
        rcode = db.insert_order_item(
            watch_item,
            quantity,
            next_order_id
        )

        if rcode == -1:
            return -1

    db.insert_order_tracking(next_order_id, "in progress")

    return next_order_id    


def track_order(parameters: dict, session_id: str):
    order_id = int(parameters['order_id'])
    order_status =db.get_order_status(order_id)

    if order_status:
        fulfillmentText = f"The order status of order id: {order_id} is {order_status}"
    else:
        fulfillmentText = f"NO order found with order id: {order_id}"

    return JSONResponse(content={
            "fulfillmentText": fulfillmentText
    })
    
