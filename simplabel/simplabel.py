import tkinter as tk
from tkinter.messagebox import askquestion
from PIL import Image,ImageTk
import os
from functools import partial
import pickle
import time
import sys
import logging
import random


class ImageClassifier(tk.Frame):
    """
    Manually label images from a folder into arbitrary categories
    
    Parameters
    ----------
    parent : tkinter.TK()
        tkinter instance
    directory : string
        Directory to explore for the images to label (must contain only image files)
    categories : list[string]
        Disting categories to use for labelling
    verbose : int
        Logging level, 0: WARNING, 1: INFO, 2: DEBUG
    username : str
        Username to be used for multi-user mode
    autoRefresh : int
        Interval in seconds between auto-save and auto-refresh of master dict actions (0 to disable)

    Notable attributes
    -------
    labelled : dict(string: string)
        Dictionary containing the labels in the form {'image_name.jpg': label}
        This dict is saved to disk by the 'Save' button
    """

    def __init__(self, parent, directory, categories = None, verbose = 0, username = None, reconcileMode = False, autoRefresh = 60, *args, **kwargs):

        # Initialize frame
        tk.Frame.__init__(self, parent, *args, **kwargs)

        # Initialize logger
        verbose = 2 # FIXME: verbosity is set to debug level
        if verbose == 1:
            logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
        elif verbose == 2:
            logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(message)s')
        else:
            logging.basicConfig(level=logging.WARNING, format='%(levelname)s - %(message)s')

        self.root = parent
        self.root.wm_title("Simplabel")

        # Supported image file formats (all extensions supported by PIL should work)
        self.supported_extensions = ['jpg','JPG','png','gif','JPEG','eps','bmp','tiff']

        # Define colors to be used for users
        self.colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

        # Window Dimensions
        self.winwidth = 1000
        self.imwidth = self.winwidth - 10
        self.imheight = int(self.imwidth // 1.5)

        #  Directory containing the raw images
        self.folder = directory

        # Directory containing the labels
        self.labelpath = self.folder + "/labels.pkl"

        # Initialize a refresh timestamp and refresh interval for auto-save and auto-refresh master dict
        self.saveTimestamp = time.time()
        self.saveInterval = autoRefresh
        self.refreshTimestamp = time.time()
        self.refreshInterval = autoRefresh

        # Make a frame for global control buttons (at the top of the window)
        self.frame0 = tk.Frame(self.root, width=self.winwidth, height=24, bd=2)
        self.frame0.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Make a frame to display the image
        self.frame1 = tk.Frame(self.root, width=self.winwidth, height=self.imheight+10, bd=2)
        self.frame1.pack(side=tk.TOP)

        # Create a canvas for the image
        self.cv1 = tk.Canvas(self.frame1, width=self.imwidth, height=self.imheight, background="white", bd=1, relief=tk.RAISED)
        self.cv1.pack(in_=self.frame1)

        # Make a frame to display the labelling buttons (at the bottom)
        self.frame2 = tk.Frame(self.root, width=self.winwidth, height=10, bd=2)
        self.frame2.pack(side = tk.BOTTOM, fill=tk.BOTH, expand=True)

        # Create the global buttons
        tk.Button(self.root, text='Exit', height=2, width=8, command =self.exit).pack(in_=self.frame0, side = tk.RIGHT)
        tk.Button(self.root, text='Reset', height=2, width=8, command =self.reset_session).pack(in_=self.frame0, side = tk.RIGHT)
        tk.Button(self.root, text='DELETE ALL', height=2, width=10, command =self.delete_saved_data).pack(in_=self.frame0, side = tk.RIGHT)

        # Create the key bindings
        self.root.bind("<Key>", self.keypress_handler)
        self.root.bind("<Left>", self.previous_image)
        self.root.bind("<Right>", self.next_image)

        # Find all labelers (other users)
        self.users = [f.split('_')[1].split('.')[0] for f in os.listdir(self.folder) if (f.endswith('.pkl') and f.startswith('labeled_'))]
        logging.info("Existing users: {}".format(self.users))

        # Assign a color for each user
        # TODO: Rewrite to ensure each user has a separate color if possible
        self.userColors = {user: self.user_color_helper(user) for user in self.users}

        # Reconcile mode state parameter
        self.reconcileMode = reconcileMode
        if reconcileMode:
            # Initialize reconcile mode
            logging.info("Starting in reconcile mode")
            self.initialize_reconcile_mode()
        else:
            # Initialize normal mode
            logging.info("Starting in labelling mode")
            self.initialize_normal_mode(directory, categories, username)


    def initialize_normal_mode(self, directory, categories, username):
        # Set the username for the current session
        if isinstance(username, str):
            # Sanitize: lowercase and remove spaces
            sanName = ''.join(username.strip().lower().split())
            # Check that username is not reserved
            if sanName == 'master':
                logging.error("Username 'master' is reserved.")
                newName = input("Please choose another name: ")
                sanName = ''.join(newName.strip().lower().split())
            self.username = sanName
            logging.info("Username: {}".format(self.username))
        else:
            # TODO: Rewrite to use hostname / system username if no username is passed
            self.username = "guest"
            logging.info("No username passed, saving as guest")

        # Choose a color for the user and make sure user is in self.users
        if self.username in self.users:
            self.userColor = self.userColors[self.username]
        else:
            self.users.append(self.username)
            self.userColor = self.user_color_helper(self.username)
            self.userColors[self.username] = self.userColor

        # Directory containing the saved labeled dictionary
        ## Note: username will be "guest" if none was passed as command line argument
        self.savepath = self.folder + "/labeled_" + self.username +".pkl"

        # Initialize state variables
        self.saved = True

        # Create the user action buttons
        self.saveButton = tk.Button(self.root, text='Save', height=2, width=8, command =self.save)
        self.saveButton.pack(in_=self.frame0, side = tk.LEFT)
        self.prevButton = tk.Button(self.root, text='Previous', height=2, width=8, command =self.previous_image)
        self.prevButton.pack(in_=self.frame0, side = tk.LEFT)
        self.nextButton = tk.Button(self.root, text='Next', height=2, width=8, command =self.next_image)
        self.nextButton.pack(in_=self.frame0, side = tk.LEFT)
        tk.Button(self.root, text='Next unlabeled', height=2, width=8, wraplength=80, command =self.goto_next_unlabeled).pack(in_=self.frame0, side = tk.LEFT)
        self.buttonOrigColor = self.saveButton.config()['highlightbackground'][-1]

        # Create a textbox for the current image information
        self.infoText = tk.Text(self.root, height=2, width=65, wrap=None)
        self.infoText.pack(in_=self.frame0)
        self.infoText.tag_config("c", justify=tk.CENTER)
        self.infoText.tag_config("r", foreground="#8B0000")
        self.infoText.tag_config("u", underline=1, foreground = self.userColor)

        ## Create user color tags
        for (user, color) in self.userColors.items():
            self.infoText.tag_config("{}Color".format(user), foreground=color)

        ## Print the name of the current user 
        self.infoText.insert('2.0', "\nLabelers: ", 'c')
        self.infoText.insert(tk.END, "{}".format(self.username), ('c', '{}Color'.format(self.username), 'u'))

        ## Print the names of other labelers
        for user in self.users:
            if user != self.username:
                self.infoText.insert(tk.END, ", ", ('c',))
                self.infoText.insert(tk.END, "{}".format(user), ('c', '{}Color'.format(user)))

        ## Disable the textbox
        self.infoText.config(state=tk.DISABLED)

        # Categories for the labelling task
        self.labels_from_file = False
        self.categories = categories
        self.initialize_labels()

        # Initialize data
        self.initialize_data()

        # Create a button for each of the categories
        self.catButton = []
        for idx, category in enumerate(self.categories):
            txt = category + " ({})".format(idx+1)
            self.catButton.append(tk.Button(self.root, text=txt, height=2, width=8, command = partial(self.classify, category)))
            self.catButton[idx].pack(in_=self.frame2, fill = tk.X, expand = True, side = tk.LEFT)
        
        # Display the first image
        self.display_image()

    def initialize_reconcile_mode(self, directory):
        pass

        # TODO: 
        # - load labeled dictionaries for each user
        # - load categories from these dictionaries
        # - Create user action buttons
        # - Create textbox
        # - Print user names in color
        # - Load images from directory
        # - Sort images: agree, disagree, unlabeled
        # - Create category buttons

    def initialize_labels(self):
        '''Loads labels from file if it exists or use labels passed as argument (these override any file defined labels).'''
        # Passed labels override any existing file
        if not self.categories:
            # Check for label file and load if it exists
            if os.path.isfile(self.labelpath):
                with open(self.labelpath,"rb") as f:
                    self.categories = pickle.load(f)
                self.labels_from_file = True
                logging.info("Loaded categories from file: {}".format(self.categories))
            # Exit if no labels are found
            else:
                logging.warning("No categories provided. Exiting.")
                self.errorClose()
        # If labels are passed, use these and save them to file
        else:
            # Add default categories
            self.categories.append('Remove')
            logging.info("Using categories passed as argument: {}".format(self.categories))
        

    def initialize_data(self):
        '''Loads existing data from disk if it exists and loads a list of unlabelled images found in the directory'''
        # Initialize current user's dictionary (Note: it might not exist yet)
        if os.path.isfile(self.savepath):
            self.labeled = self.load_dict(self.savepath)
            logging.info("Loaded existing dictionary from disk")
            # Check that the categories used in the dictionary are in self.categories
            if any([val not in self.categories for val in self.labeled.values()]):
                logging.warning("Labels in dictionary do not match passed categories")
                logging.warning("Labels in dictionary: {}".format(set(self.labeled.values())))
                logging.warning("Categories passed: {}".format(self.categories))
                self.errorClose()
        else:
            self.labeled = {}
            logging.info("No dictionary found, initializing a new one")

        # Load data from all users
        self.update_master_dict()

        # All checks for label consistency are over, save labels to file if they were passed as arguments
        if not self.labels_from_file:
            with open(self.labelpath,'wb') as f:
                pickle.dump(self.categories, f)

        # Build list of images to classify
        self.image_list = []

        ## If the directory contains at least 1 image, process only this directory
        list_image_files = [d for d in os.listdir(self.folder) if d.split('.')[-1] in self.supported_extensions]
        if len(list_image_files) > 0:
            labeledByCurrentUser = []
            labeledByOtherUser = []
            toLabel = []
            for img in list_image_files:
                if img in self.labeled:
                    labeledByCurrentUser.append(img)
                elif img in self.masterLabeled:
                    labeledByOtherUser.append(img)
                else:
                    toLabel.append(img)
        ## Otherwise, list and check subdirectories
        else:
            logging.info("No image files in main directory, searching sub-directories...")
            labeledByCurrentUser = []
            labeledByOtherUser = []
            toLabel = []
            sub_folder_list = [dirName for dirName in next(os.walk(self.folder))[1] if not dirName.startswith('.')]
            for dirName in sub_folder_list:
                dir_path = os.path.join(self.folder, dirName)
                list_image_files = [d for d in os.listdir(dir_path) if d.split('.')[-1] in self.supported_extensions]
                for img in list_image_files:
                    imgPath = dirName + '/' + img
                    if imgPath in self.labeled:
                        labeledByCurrentUser.append(imgPath)
                    elif imgPath in self.masterLabeled:
                        labeledByOtherUser.append(imgPath)
                    else:
                        toLabel.append(imgPath)

        # Images that are already labeled are concatenated with the ones labeled by the current user last to enable them to review their own labelling
        alreadyLabeled = labeledByOtherUser + labeledByCurrentUser

        # Initialize counter at the numer of already labeled images
        self.counter = len(alreadyLabeled)

        # Add already labeled images first, images to label are shuffled 
        random.seed() # Reset the random seed
        random.shuffle(toLabel) # Shuffle the list in place
        self.image_list = alreadyLabeled + toLabel

        # Check that there is at least one image
        if len(self.image_list) == 0:
            logging.warning("No images found in directory.")
            self.errorClose()
        else:
            logging.info("Found {} images under the directory: {}".format(len(self.image_list), self.folder))
            logging.info("{} images left to label".format(len(self.image_list)-self.counter))

        # Get number of images   
        self.max_count = len(self.image_list)-1

    def classify(self, category):
        '''Adds a directory entry with the name of the image and the label selected'''
        if self.counter > self.max_count:
            logging.info("No more images to label")
        else:
            self.labeled[self.image_list[self.counter]] = category
            logging.info('Label {} selected for image {}'.format(category, self.image_list[self.counter]))
            if self.saved: # Reset saved status
                self.saved = False
            
            # If it is time to refresh the master, do that
            # Note: after the refresh, the counter will be at the next unlabeled position
            if self.refreshInterval != 0 and (time.time() - self.refreshTimestamp > self.refreshInterval):
                logging.debug("classify - Triggered auto-refresh")
                self.refreshTimestamp = time.time()
                self.refresh_master()
                self.display_image()
            else:
                self.next_image()
            
    
    def update_master_dict(self):
        '''Loads the labeling data from all detected users into a master dictionary.

        self.masterLabeled: {picName: [(user, label)]}
        '''
        self.masterLabeled = {}
        for user in self.users:
            # Current user is treated separately because dict is already loaded and might not exist on disk
            if user == self.username:
                for (imageName, label) in self.labeled.items():
                    self.masterLabeled[imageName] = [(user, label)]
            # For other users, load their dict and dump data into the masterLabeled dictionary
            else:
                dictPath = self.folder + "/labeled_" + user +".pkl"
                userDict = self.load_dict(dictPath)
                for (imageName, label) in userDict.items():
                    if imageName in self.masterLabeled:
                        self.masterLabeled[imageName].append((user, label))
                    else:
                        self.masterLabeled[imageName] = [(user, label)]

    def refresh_master(self):
        '''Updates the master dictionary and refreshes the img_list accordingly. Does not re-explore the directory.'''

        # Update the master dict by refreshing it
        self.update_master_dict()

        # Rebuild the image_list
        labeledByCurrentUser = []
        labeledByOtherUser = []
        toLabel = []
        for img in self.image_list:
            if img in self.labeled:
                labeledByCurrentUser.append(img)
            elif img in self.masterLabeled:
                labeledByOtherUser.append(img)
            else:
                toLabel.append(img)
        
        alreadyLabeled = labeledByOtherUser + labeledByCurrentUser
        self.counter = len(alreadyLabeled)
        self.image_list =  alreadyLabeled + toLabel

        

    def previous_image(self, *args):
        '''Displays the previous image'''
        if self.counter > 0:
            self.counter += -1
            self.display_image()
        else:
            logging.info("This is the first image, can't go back")
    
    def next_image(self, *args):
        '''Displays the next image'''
        if self.counter <= self.max_count:
            self.counter += 1
            self.display_image()
        else:
            logging.info("No more images")

    def goto_next_unlabeled(self):
        '''Displays the unlabeled image with the smallest index number'''
        for idx, img in enumerate(self.image_list):
            if img not in self.labeled and img not in self.masterLabeled:
                self.counter = idx
                self.display_image()
                break

    def display_image(self):
        '''Displays the image corresponding to the current value of the counter'''

        # If the counter overflows, go back to the last image
        if self.counter > self.max_count and self.max_count > -1:
            logging.debug("display_image - Counter overflowed")
            self.counter = self.max_count
            self.display_image()
        # If there are no images to label, exit
        elif self.max_count == 0:
            logging.warning("No images to label")
            self.errorClose()
        else:
            img = self.image_list[self.counter] # Name of current image
            self.im = Image.open("{}{}".format(self.folder + '/', img))
            if (self.imwidth-self.im.size[0])<(self.imheight-self.im.size[1]):
                width = self.imwidth
                height = width*self.im.size[1]/self.im.size[0]
            else:
                height = self.imheight
                width = height*self.im.size[0]/self.im.size[1]
            
            self.im.thumbnail((width, height), Image.ANTIALIAS)
            self.photo = ImageTk.PhotoImage(self.im)

            if self.counter == 0:
                self.cv1.create_image(0, 0, anchor = 'nw', image = self.photo)

            else:
                self.cv1.delete("all")
                self.cv1.create_image(0, 0, anchor = 'nw', image = self.photo)

            # Edit the text information
            self.infoText.config(state=tk.NORMAL)
            self.infoText.delete('1.0', '1.end')
            self.infoText.insert('1.0',"Image {}/{} - Filename: {}".format(self.counter+1,self.max_count+1,img), 'c')
            self.infoText.config(state=tk.DISABLED)

            # Reset all button styles (colors and outline)
            self.saveButton.config(highlightbackground = self.buttonOrigColor)
            for i in range(len(self.catButton)):
                self.catButton[i].config(highlightbackground = self.buttonOrigColor)

            # Display the associated label(s) from any user as colored background for the label button
            if img in self.masterLabeled:
                labelDict = {}
                for (user, label) in self.masterLabeled[img]:
                    if label in labelDict:
                        labelDict[label].append(self.userColors[user])
                    else:
                        labelDict[label] = [self.userColors[user]]
                # The img might be in self.labeled but not yet in self.masterLabeled (between updates of masterDict)
                if img in self.labeled:
                    label = self.labeled[img]
                    if label in labelDict and self.userColor not in labelDict[label]:
                        labelDict[label].append(self.userColor)
                    else:
                        labelDict[label] = [self.userColor]
                for label in labelDict:
                    idxLabel = self.categories.index(label)
                    if len(labelDict[label]) == 1:
                        self.catButton[idxLabel].config(highlightbackground=labelDict[label][0])
                    else:
                        self.catButton[idxLabel].config(highlightbackground='#3E4149')
            elif img in self.labeled:
                label = self.labeled[img]
                idxLabel = self.categories.index(label)
                self.catButton[idxLabel].config(highlightbackground=self.userColor)

            # Disable back button if on first image
            if self.counter == 0:
                self.prevButton.config(state = tk.DISABLED)
            else:
                self.prevButton.config(state = tk.NORMAL)

            # Disable next button on last image
            if self.counter == self.max_count:
                self.nextButton.config(state = tk.DISABLED)
            else:
                self.nextButton.config(state = tk.NORMAL)

            # Auto-save and auto-refresh
            if self.saveInterval != 0 and (time.time() - self.saveTimestamp) > self.saveInterval:
                logging.debug("display_image - Auto-save triggered")
                self.saveTimestamp = time.time()
                self.save()


    def keypress_handler(self,e):
        try:
            cat = int(e.char) - 1
            if cat in range(len(self.categories)):
                self.classify(self.categories[cat])
        except ValueError:
            if e.char == 's':
                self.save()
            elif e.char == 'q':
                self.exit()
            elif e.char == 'r':
                self.reset_session()
            else:
                pass
    
    def save(self):
        '''Save the labeled dictionary to disk'''
        self.dump_dict(self.labeled, self.savepath)
        self.saveButton.config(highlightbackground='#3E4149')
        self.saved = True
        logging.info("Saved data to file")
    
    def load_dict(self, file):
        '''Read a pickeled dictionary from file'''
        with open(file,"rb") as f:
            return pickle.load(f)
    
    def dump_dict(self, dict, file):
        '''Pickle a dictionary to file'''
        with open(file, 'wb') as f:
            pickle.dump(dict, f)

    def user_color_helper(self, username):
        random.seed(a = username)
        return random.choice(self.colors)

    def reset_session(self):
        '''Deletes all labels from the current session and reload the images'''
        result = askquestion('Are you sure?', 'Delete data since last save?', icon = 'warning')
        if result == 'yes':
            logging.warning("Resetting session since last save and reinitializing date")
            self.labeled = {}
            self.initialize_data()
            self.display_image()
        else:
            pass
    
    def delete_saved_data(self):
        '''Deletes all labels from session and saved data then closes the app'''
        result = askquestion('Are you sure?', 'This action will delete all saved and session data for this user and quit the app. Continue?', icon = 'warning')
        if result == 'yes':
            logging.warning("Deleting all saved data and exiting")
            if os.path.isfile(self.savepath):
                os.remove(self.savepath)
            if os.path.isfile(self.labelpath):
                os.remove(self.labelpath)
            self.errorClose()
        else:
            pass

    def exit(self):
        '''Cleanly exits the app'''
        if not self.saved:
            result = askquestion('Save?', 'Do you want to save this session before leaving?', icon = 'warning')
            if result == 'yes':
                self.save()
        self.quit()

    def errorClose(self):
        '''Closes the window when the app encouters an error it cannot recover from'''
        logging.info("Closing the app...")
        self.master.destroy()
        sys.exit()

if __name__ == "__main__":
    root = tk.Tk() 
    rawDirectory = "data/raw"
    categories = ['Crystal', 'Clear']
    MyApp = ImageClassifier(root, rawDirectory, categories, 2)
    tk.mainloop()