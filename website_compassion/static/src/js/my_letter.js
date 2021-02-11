/**
 * This function replaces a range in a string
 * @param from the starting point of the substitution
 * @param to the end point of the substitution, can be -1 to drop the rest
 * @param substitute the substitution to use
 * @returns {string} a new string substituted with the desired content
 */
String.prototype.replaceRange = function(from, to, substitute) {
    var result = this.substring(0, from) + substitute;
    if (to != -1) {
        result += this.substring(to)
    }
    return result;
}

/**
 * Returns the last index of a substring found in a string or -1
 * @param substring the substring to find inside the string object
 * @returns {number|*} -1 if the substring is not in the string or the index
 */
String.prototype.indexOfEnd = function(substring) {
    const index = this.indexOf(substring);
    return index === -1 ? index : index + substring.length;
}

/**
 * Selects the element given the element type and the object id. This relies
 * on a smart choice of ids in the XML file.
 * @param obj_id the id of the object to select
 * @param elem_type the type of the object to select
 */
selectElement = function(obj_id, elem_type) {
    // The id in the XML must have this form precisely, for this to work.
    const elem_id = `${elem_type}_${obj_id}`;
    // Elements are selected by finding the corresponding image and setting
    // the border around the selected one
    const elements = document.querySelectorAll(`img[class~="${elem_type}-image"]`);

    for (var i = 0 ; i < elements.length ; i++) {
        var element = elements[i];

        // Remove the border when not selected
        if (element.id !== elem_id) {
            element.classList.remove("border");
            element.classList.remove("border-5");
            element.classList.remove("border-primary");
            continue;
        }

        // Add border to selected child
        element.classList.add("border");
        element.classList.add("border-5");
        element.classList.add("border-primary");

        // Change url to display selected child and template id
        const base_url = window.location.origin + window.location.pathname;
        var params = window.location.search;
        const from = params.indexOfEnd(`${elem_type}_id=`);
        if (from === -1) {
            params += `&${elem_type}_id=${obj_id}`;
        } else {
            const to = params.indexOf("&", from);
            params = params.replaceRange(from, to, obj_id);
        }
        // We use replaceState for refreshes to work as intended
        history.replaceState({}, document.title, base_url + params);

        // Scroll smoothly to selected child
        const card = document.getElementById(`card_${elem_type}_${obj_id}`);
        card.scrollIntoView({
            behavior: "smooth",
            block: "nearest",
            inline: "start",
        });

        // We correctly set some values for letter writing to work properly
        const name = document.getElementById(`${elem_type}_name_${obj_id}`).attributes.value.value;
        const local_id = document.getElementById(`${elem_type}_local_id_${obj_id}`);
        if (local_id) {
            document.getElementById(`${elem_type}_local_id`).attributes.value.value = local_id.attributes.value.value;
        }
        document.getElementById(`${elem_type}_id`).attributes.value.value = obj_id;
        document.getElementById(`${elem_type}_name`).attributes.value.value = name;
    }
}

const max_size = 1000;
/**
 * This function compresses images that are too big by shrinking them and if
 * necessary compressing using JPEG
 * @param image the image to compress
 * @returns {Promise<unknown>} the image as a promised blob (to allow
 * asynchronous calls)
 */
const compressImage = async function(image) {
    var canvas = document.createElement('canvas');

    var width = image.width;
    var height = image.height;

    // calculate the width and height, constraining the proportions
    const min_width = Math.min(width, max_size);
    const min_height = Math.min(height, max_size);
    const factor = Math.min(min_width / width, min_height / height);

    // resize the canvas and draw the image data into it
    canvas.width = Math.floor(width * factor);
    canvas.height = Math.floor(height * factor);
    var ctx = canvas.getContext("2d");
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);

    return await new Promise(resolve => ctx.canvas.toBlob(resolve, "image/jpeg"));
}

/**
 * Returns the index of the file in the array object, given some of its
 * characteristics
 * @param name the name of the file
 * @param size the size of the file
 * @param type the type of the file
 * @returns {number} the index if found or -1, else
 */
Array.prototype.indexOfFile = function(name, size, type) {
    for (var i = 0 ; i < this.length ; i++) {
        const f = this[i];
        if (f.name === name && f.size === size && f.type === type) {
            return i;
        }
    }
    return -1;
}

/**
 * Check whether a file is contained in the array object
 * @param name the name of the file
 * @param size the size of the file
 * @param type the type of the file
 * @returns {boolean} true if the file is contained in the array or false
 */
Array.prototype.containsFile = function(name, size, type) {
    return this.indexOfFile(name, size, type) !== -1;
}

/**
 * Remove the file of the array object, or does nothing if it is not contained
 * @param name the name of the file
 * @param size the size of the file
 * @param type the type of the file
 */
const removeFile = function(name, size, type) {
    if (images_list.containsFile(name, size, type)) {
        const index = images_list.indexOfFile(name, size, type);
        images_list.splice(index, 1);
        images_comp.splice(index, 1);
    }
}

/**
 * Remove the image from the array as well as the HTML page
 * @param name the name of the file
 * @param size the size of the file
 * @param type the type of the file
 */
const removeImage = function(name, size, type) {
    removeFile(name, size, type);
    document.getElementById(`${name}_${size}_${type}`).remove();
}

/**
 * Display the images contained in new_images inside the HTML page
 */
const displayImages = function() {
    const image_display = document.getElementById("image_display_table");

    // We use the images stored in the new_images array
    for (var i = 0 ; i < new_images.length ; i++) {
        const original_image = new_images[i];

        const reader = new FileReader();
        reader.onload = function(event) {
            var image = new Image();
            image.src = event.target.result;
            image.onload = function(event) {
                if (original_image.size > 2e5) {
                    compressImage(image).then((blob) => {
                        blob.name = original_image.name;
                        blob.lastModified = Date.now();
                        blob.webkitRelativePath = "";
                        images_comp = images_comp.concat(blob);
                    })
                } else {
                    images_comp = images_comp.concat(original_image);
                }

                image_display.innerHTML += `
                    <div id="${original_image.name}_${original_image.size}_${original_image.type}" class="w-100">
                        <li class="embed-responsive-item p-2" style="position: relative;">
                            <span class="close close-image p-2" onclick="removeImage('${original_image.name}', ${original_image.size}, '${original_image.type}');">&times;</span>
                            <img class="text-center" src="${image.src}" alt="${original_image.name}" style="width: 100%; height: auto;"/>
                        </li>
                    </div>
                `;
            };
        }
        reader.readAsDataURL(original_image);
    }

    new_images = [];
}

// The images compressed
var images_comp = [];
// The list of images actually displayed inside the view
var images_list = [];
// The new non-duplicated images to add to the view
var new_images = [];

/**
 * Handle the addition of new images and ignore the duplications
 * @param event the event containing the file, among other things
 */
document.getElementById("file_selector").onchange = function(event) {
    var input_images = event.target.files;

    // TODO CI-765: remove the following block to support multiple images
    for (var i = 0 ; i < images_list.length ; i++) {
        const file = images_list[i];
        removeImage(file.name, file.size, file.type);
    }
    // TODO CI-765: end of block

    for (var i = 0 ; i < input_images.length ; i++) {
        const file = input_images[i];
        if (!images_list.containsFile(file.name, file.size, file.type)) {

            new_images = new_images.concat(file);
            images_list = images_list.concat(file);
        }
    }

    // TODO CI-765: uncomment the following block to support multiple images
    /*
    if (new_images.length > 0) {
        display_alert("letter_images_duplicated");
        return;
    }
    */
    // TODO CI-765: end of block

    displayImages();
}

var loading = false;
/**
 * Starts and end the loading of the type elements
 * @param type the type of elements to start or stop loading
 */
const startStopLoading = function(type) {
    loading = !loading;
    $("button").attr('disabled', loading);
    if(loading) {
        document.getElementById(`${type}_normal`).style.display = "none";
        document.getElementById(`${type}_loading`).style.display = "";
    } else {
        document.getElementById(`${type}_loading`).style.display = "none";
        document.getElementById(`${type}_normal`).style.display = "";
    }
}

/**
 * Create a new letter object in the database
 * @param preview boolean to determine whether we want to see the preview
 * @param with_loading determines whether we want to have a loading or not
 * @returns {Promise<unknown>} return the entire method as a promise so that
 * we can send a letter directly if the user pressed the corresponding button
 */
const createLetter = async function(preview=false, with_loading=true) {
    return new Promise(function(resolve) {
        if (with_loading) {
            startStopLoading("preview");
        }
        var form_data = new FormData();

        form_data.append("letter-copy", document.getElementById('letter_content').value);
        form_data.append("selected-child", document.getElementById('child_local_id').attributes.value.value);
        form_data.append("selected-letter-id", document.getElementById('template_id').attributes.value.value);
        form_data.append("source", "website");
        // TODO CI-765: Handle properly multiple images
        if (images_list.length > 0) {
            form_data.append("file_upl", images_comp[0]);
        }
        // TODO CI-765: end of block

        var xhr = new XMLHttpRequest();
        var url = `${window.location.origin}/mobile-app-api/correspondence/get_preview`;
        xhr.open("POST", url, true);
        xhr.onreadystatechange = function () {
            if (xhr.readyState === 4 && xhr.status === 200) {
                if (preview) {
                    if (with_loading) {
                        startStopLoading("preview");
                    }
                    window.open(xhr.responseText.slice(1, -1), "_blank");
                }
                resolve();
            }
        };
        xhr.send(form_data);
    })
}

/**
 * This function takes care of sending a letter when the corresponding button
 * is clicked
 */
const sendLetter = async function() {
    startStopLoading("sending");
    await createLetter(preview=false, with_loading=false);

    var json_data = JSON.parse(`{
        "TemplateID": "${document.getElementById('template_id').attributes.value.value}",
        "Need": "${document.getElementById('child_id').attributes.value.value}"
    }`);

    var xhr = new XMLHttpRequest();
    var url = `${window.location.origin}/mobile-app-api/correspondence/send_letter`;
    xhr.open("POST", url, true);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.onreadystatechange = function () {
        if (xhr.readyState === 4 && xhr.status === 200) {
            startStopLoading("sending");
            // Empty images and text (to avoid duplicate)
            document.getElementById("letter_content").value = ""
            for (var i = 0 ; i < images_list.length ; i++) {
                var image = images_list[i];
                removeImage(image.name, image.size, image.type);
            }

            displayAlert("letter_sent_correctly");
        }
    };
    xhr.send(JSON.stringify(json_data));
}
